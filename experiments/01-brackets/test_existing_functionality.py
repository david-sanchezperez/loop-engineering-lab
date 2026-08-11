#!/usr/bin/env python3
"""
Test script to verify that the existing functionality still works
and that normal LLM calls are not affected by our changes.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add the experiment directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from loop import extract_code, run_loop_claude, run_loop_local


class TestExistingFunctionality(unittest.TestCase):
    """Test cases to verify existing functionality still works"""

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

    def test_code_extraction_still_works(self):
        """Test that code extraction from LLM responses still works"""
        response = """Here's the code:
```python
def is_balanced(s):
    return True
```

Some explanation here."""
        code = extract_code(response)
        self.assertIn("def is_balanced(s):", code)
        self.assertNotIn("Some explanation", code)

    def test_normal_local_llm_flow(self):
        """Test that normal LLM flow for local backend still works"""
        
        # Mock successful LLM response and successful test
        with patch('loop._call_local') as mock_call, \
             patch('loop.run_tests') as mock_tests:
            
            mock_call.return_value = """```python
def is_balanced(s):
    stack = []
    mapping = {')': '(', ']': '[', '}': '{'}
    for char in s:
        if char in mapping.values():
            stack.append(char)
        elif char in mapping:
            if not stack or stack.pop() != mapping[char]:
                return False
    return not stack
```"""
            
            mock_tests.return_value = (True, "")  # Success
            
            result = run_loop_local(max_iters=10, run_id=1)
            
            # Should succeed on first iteration
            self.assertTrue(result['success'])
            self.assertEqual(result['iterations'], 1)
            self.assertEqual(result['stop_reason'], 'success')
            
            # Verify LLM was called once
            mock_call.assert_called_once()
            
            # Verify tests were run once
            mock_tests.assert_called_once()

    def test_normal_claude_llm_flow(self):
        """Test that normal LLM flow for Claude backend still works"""
        
        # Mock successful LLM response and successful test
        with patch('loop._call_claude') as mock_call, \
             patch('loop.run_tests') as mock_tests:
            
            # Mock Claude response with tokens and cost
            mock_call.return_value = ("""```python
def is_balanced(s):
    stack = []
    mapping = {')': '(', ']': '[', '}': '{'}
    for char in s:
        if char in mapping.values():
            stack.append(char)
        elif char in mapping:
            if not stack or stack.pop() != mapping[char]:
                return False
    return not stack
```""", 100, 50, 0.01)
            
            mock_tests.return_value = (True, "")  # Success
            
            result = run_loop_claude(max_iters=10, budget_usd=0.10, run_id=1)
            
            # Should succeed on first iteration
            self.assertTrue(result['success'])
            self.assertEqual(result['iterations'], 1)
            self.assertEqual(result['stop_reason'], 'success')
            
            # Verify LLM was called once
            mock_call.assert_called_once()
            
            # Verify tests were run once
            mock_tests.assert_called_once()
            
            # Verify cost tracking
            self.assertEqual(result['input_tokens'], 100)
            self.assertEqual(result['output_tokens'], 50)
            self.assertAlmostEqual(result['cost_usd'], 0.01)

    def test_circuit_breaker_still_works_for_test_failures(self):
        """Test that circuit breaker still works for repeated test failures"""
        
        with patch('loop._call_local') as mock_call, \
             patch('loop.run_tests') as mock_tests:
            
            # Mock LLM response
            mock_call.return_value = """```python
def is_balanced(s):
    return False  # Wrong implementation
```"""
            
            # Mock repeated test failures with same error
            mock_tests.return_value = (False, "FAIL: test case 1")
            
            result = run_loop_local(max_iters=10, run_id=1)
            
            # Should fail with circuit breaker after 3 attempts
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'circuit_breaker')
            self.assertEqual(result['iterations'], 3)

    def test_step_cap_still_works(self):
        """Test that step cap still works"""
        
        with patch('loop._call_local') as mock_call, \
             patch('loop.run_tests') as mock_tests:
            
            # Mock LLM response
            mock_call.return_value = "```python\ndef is_balanced(s):\n    return False\n```"
            
            # Mock test failures with different errors each time (so circuit breaker doesn't trigger)
            error_count = [0]
            def mock_tests_side_effect(code, error_count=error_count):
                error_count[0] += 1
                return (False, f"FAIL: test case {error_count[0]}")
            
            mock_tests.side_effect = mock_tests_side_effect
            
            result = run_loop_local(max_iters=5, run_id=1)
            
            # Should fail with step_cap after 5 iterations
            self.assertFalse(result['success'])
            self.assertEqual(result['stop_reason'], 'step_cap')
            self.assertEqual(result['iterations'], 5)


if __name__ == '__main__':
    unittest.main()
