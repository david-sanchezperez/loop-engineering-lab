#!/usr/bin/env python3
"""
Test script to verify that the loop harness properly handles LLM failures
without wasting retries or attempting to continue when the LLM is down.

This test simulates scenarios where:
1. The LLM API is unreachable (connection error)
2. The LLM API times out
3. The LLM returns an error response

The test verifies that:
- The system properly detects LLM failures
- No unnecessary retries are consumed when the LLM is down
- The loop exits gracefully with appropriate stop_reason
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add the experiment directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from loop import CIRCUIT_BREAKER_THRESHOLD, run_loop_claude, run_loop_local


class TestLLMFailureHandling(unittest.TestCase):
    """Test cases for LLM failure scenarios"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.results_dir.mkdir()
        
        # Mock the STATE_FILE to use our temp directory
        patcher = patch('loop.RESULTS_DIR', self.results_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_local_llm_connection_error(self):
        """Test that connection errors to local LLM are handled properly"""
        
        with patch('loop._call_local') as mock_call:
            # Simulate connection error
            mock_call.side_effect = Exception("Connection error: localhost:4000")
            
            result = run_loop_local(max_iters=3, run_id=1)
            
            # Should fail but not waste multiple retries
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'circuit_breaker')
            self.assertLessEqual(result['iterations'], CIRCUIT_BREAKER_THRESHOLD)
            
    def test_local_llm_timeout(self):
        """Test that timeout errors to local LLM are handled properly"""
        
        with patch('loop._call_local') as mock_call:
            # Simulate timeout
            mock_call.side_effect = Exception("Timeout error")
            
            result = run_loop_local(max_iters=5, run_id=1)
            
            # Should fail with circuit breaker before exhausting all iterations
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'circuit_breaker')
            self.assertLessEqual(result['iterations'], CIRCUIT_BREAKER_THRESHOLD)

    def test_local_llm_api_error_response(self):
        """Test that API error responses from local LLM are handled properly"""
        
        with patch('loop._call_local') as mock_call:
            # Simulate API error response
            mock_call.side_effect = Exception("API error: 503 Service Unavailable")
            
            result = run_loop_local(max_iters=10, run_id=1)
            
            # Should fail with circuit breaker
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'circuit_breaker')
            self.assertLessEqual(result['iterations'], CIRCUIT_BREAKER_THRESHOLD)

    def test_claude_llm_connection_error(self):
        """Test that connection errors to Claude API are handled properly"""
        
        with patch('loop._call_claude') as mock_call:
            # Simulate connection error
            mock_call.side_effect = Exception("Connection error: Anthropic API")
            
            result = run_loop_claude(max_iters=3, budget_usd=0.10, run_id=1)
            
            # Should fail but not waste multiple retries
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'circuit_breaker')
            self.assertLessEqual(result['iterations'], CIRCUIT_BREAKER_THRESHOLD)
            
    def test_claude_llm_timeout(self):
        """Test that timeout errors to Claude API are handled properly"""
        
        with patch('loop._call_claude') as mock_call:
            # Simulate timeout
            mock_call.side_effect = Exception("Timeout error")
            
            result = run_loop_claude(max_iters=5, budget_usd=0.10, run_id=1)
            
            # Should fail with circuit breaker before exhausting all iterations
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'circuit_breaker')
            self.assertLessEqual(result['iterations'], CIRCUIT_BREAKER_THRESHOLD)

    def test_claude_llm_rate_limit_error(self):
        """Test that rate limit errors from Claude API are handled properly"""
        
        with patch('loop._call_claude') as mock_call:
            # Simulate rate limit error (which should be retryable)
            mock_call.side_effect = Exception("Rate limit exceeded")
            
            result = run_loop_claude(max_iters=10, budget_usd=0.10, run_id=1)
            
            # Should fail with circuit breaker after repeated rate limit errors
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'circuit_breaker')
            self.assertLessEqual(result['iterations'], CIRCUIT_BREAKER_THRESHOLD)

    def test_no_retry_wasted_on_llm_failure(self):
        """Test that LLM failures don't waste retry attempts"""
        
        with patch('loop._call_local') as mock_call:
            # Simulate LLM being completely down
            mock_call.side_effect = Exception("LLM service unavailable")
            
            result = run_loop_local(max_iters=10, run_id=1)
            
            # The key assertion: we should not exhaust all iterations
            # If we did, it would mean we wasted retries trying to call a down LLM
            self.assertLess(result['iterations'], 10, 
                         "Should not waste retries when LLM is down")
            self.assertLessEqual(result['iterations'], CIRCUIT_BREAKER_THRESHOLD,
                                "Should stop after circuit breaker threshold")

    def test_graceful_exit_with_appropriate_stop_reason(self):
        """Test that LLM failures result in appropriate stop_reason"""
        
        error_scenarios = [
            ("Connection refused", "circuit_breaker"),
            ("Timeout", "circuit_breaker"),
            ("Service Unavailable", "circuit_breaker"),
            ("Internal Server Error", "circuit_breaker"),
        ]
        
        for error_msg, expected_reason in error_scenarios:
            with self.subTest(error_msg=error_msg), patch('loop._call_local') as mock_call:
                mock_call.side_effect = Exception(error_msg)
                result = run_loop_local(max_iters=5, run_id=1)
                self.assertEqual(result['stop_reason'], expected_reason)


if __name__ == '__main__':
    unittest.main()
