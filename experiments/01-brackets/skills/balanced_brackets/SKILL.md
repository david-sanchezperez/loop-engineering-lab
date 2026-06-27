# Skill: is_balanced

Implementa la función `is_balanced` en Python.

## Especificación

```python
def is_balanced(s: str) -> bool:
    """
    Retorna True si los brackets en `s` están correctamente balanceados.

    Reglas:
    - Brackets soportados: (), [], {}
    - Cada bracket de apertura debe cerrarse con el tipo correcto
    - Los brackets deben cerrarse en el orden correcto (el último abierto, primero en cerrar)
    - Una cadena vacía está balanceada
    - Caracteres que no son brackets se ignoran
    """
```

## Output esperado

Devuelve SOLO la función dentro de un bloque de código Python:

```python
def is_balanced(s: str) -> bool:
    ...
```

Sin imports adicionales. Sin explicaciones. Sin texto fuera del bloque de código.

## Casos de prueba

| Input        | Resultado |
|--------------|-----------|
| `""`         | `True`    |
| `"()"`       | `True`    |
| `"()[]{}"`   | `True`    |
| `"([])"  `   | `True`    |
| `"{[()]}"`   | `True`    |
| `"([{}])"`   | `True`    |
| `"("`        | `False`   |
| `")"`        | `False`   |
| `"([)]"`     | `False`   |  ← ojo: conteos iguales pero orden incorrecto
| `"(("`       | `False`   |
| `"]"`        | `False`   |
| `"["`        | `False`   |
