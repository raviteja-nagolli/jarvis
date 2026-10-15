"""
tools/calculator_tool.py — Safe arithmetic calculator.

Supports: +, -, *, /, ** (integer exponent only), % and parentheses.
Never uses eval() on model-supplied strings.
"""
import ast
import math
import operator
import sys
from typing import Union

# Allowlisted AST node types  (ast.Num removed in Python 3.14)
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
)

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_MAX_INPUT = 1e15
_MAX_RESULT = 1e30
_MAX_EXPONENT = 100


def _eval_node(node: ast.AST) -> Union[int, float]:
    if not isinstance(node, _ALLOWED_NODES):
        raise ValueError(f"Unsupported operation: {type(node).__name__}")

    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric constants are supported")
        if abs(node.value) > _MAX_INPUT:
            raise ValueError(f"Operand {node.value} exceeds allowed magnitude")
        return node.value



    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op_fn = _OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        if isinstance(node.op, ast.Div) and right == 0:
            raise ZeroDivisionError("Division by zero is not allowed")
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_EXPONENT:
                raise ValueError(f"Exponent {right} exceeds maximum of {_MAX_EXPONENT}")
        result = op_fn(left, right)
        if abs(result) > _MAX_RESULT:
            raise ValueError("Result exceeds allowed magnitude")
        return result

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        op_fn = _OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(operand)

    raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def calculate(expression: str) -> dict:
    """
    Safely evaluate a mathematical expression.
    Returns {"result": <number>, "expression": <str>}.
    Raises ValueError or ZeroDivisionError on invalid input.
    """
    if not expression or not expression.strip():
        raise ValueError("Expression must not be empty")
    if len(expression) > 500:
        raise ValueError("Expression exceeds maximum length of 500 characters")

    expr = expression.strip()
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {exc}") from exc

    # Walk the AST and validate all nodes before evaluation
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Disallowed operation in expression: {type(node).__name__}")

    result = _eval_node(tree)
    return {"result": result, "expression": expr}


def verify_calculation(expression: str, expected_result: Union[int, float, None] = None) -> dict:
    try:
        calc = calculate(expression)
        passed = True if expected_result is None else math.isclose(
            calc["result"], expected_result, rel_tol=1e-9
        )
        return {
            "passed": passed,
            "method": "arithmetic_recompute",
            "evidence": {"result": calc["result"], "expression": calc["expression"]},
        }
    except Exception as exc:
        return {
            "passed": False,
            "method": "arithmetic_recompute",
            "evidence": {"error": str(exc)},
        }
