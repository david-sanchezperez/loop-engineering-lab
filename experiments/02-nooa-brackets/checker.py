"""checker.py — juez determinista compartido (tests de brackets en subproceso aislado).

Copiado del experimento 01 para que el experimento 02 (NOOA vs. clásico) sea
autocontenido. Ambos enfoques (NOOA y tool-calling clásico) reusan este mismo
checker, de forma que la diferencia observada entre arquitecturas se atribuya
al agente y no al juez.

El caso ``"([)]"`` es el edge case clave: conteos iguales de brackets pero
orden incorrecto, que rompe soluciones naive por conteo y fuerza un stack.

Expone:
  - ``TEST_CASES``: 15 casos de prueba ``(input, esperado)``.
  - ``run_tests(code)``: ejecuta el código del modelo en un subproceso aislado
    y retorna ``(éxito, mensaje_error)``.
"""

import os
import subprocess
import sys
import tempfile
import textwrap

TEST_CASES = [
    # vacío
    ("",        True),
    # pares simples
    ("()",      True),
    ("[]",      True),
    ("{}",      True),
    # secuencias
    ("()[]{}",  True),
    # anidados correctos
    ("([])",    True),
    ("{[()]}",  True),
    ("([{}])",  True),
    # mal anidados — este es el caso clave que rompe soluciones naive por conteo
    ("([)]",    False),
    # solo abiertos
    ("(",       False),
    ("[",       False),
    ("(()",     False),
    # solo cerrados
    (")",       False),
    ("]",       False),
    # cierre extra
    ("())",     False),
]

_TEST_HARNESS_TEMPLATE = textwrap.dedent("""\
    import sys

    {code}

    cases = {cases!r}
    errors = []
    for s, expected in cases:
        try:
            result = is_balanced(s)
        except Exception as e:
            errors.append(f"EXCEPTION en is_balanced({{s!r}}): {{e}}")
            continue
        if result != expected:
            errors.append(f"FAIL: is_balanced({{s!r}}) = {{result!r}}, esperado {{expected!r}}")

    if errors:
        print("\\n".join(errors))
        sys.exit(1)
    sys.exit(0)
""")


def run_tests(code: str) -> tuple[bool, str]:
    """Ejecuta los tests en subproceso aislado. Retorna (éxito, mensaje_error)."""
    if not code:
        return False, "El modelo no generó código (respuesta vacía o solo reasoning)"

    script = _TEST_HARNESS_TEMPLATE.format(code=code, cases=TEST_CASES)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        tmp = f.name
    try:
        r = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=10,
            check=False,
        )
        if r.returncode == 0:
            return True, ""
        return False, (r.stdout + r.stderr).strip() or "Error desconocido (exit code != 0)"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT: el script tardó más de 10 segundos"
    finally:
        os.unlink(tmp)
