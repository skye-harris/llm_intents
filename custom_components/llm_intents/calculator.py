"""Calculator tool for basic math operations."""

import ast
import logging
import operator

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)

# 1e308 = 1 * 10^308 = 1 followed by 308 zeros.
# This is the largest finite number Python can represent (float("inf") beyond this).
_MAX_EXPONENT_RESULT = 1e308

# 1e6 = 1,000,000 (one million).
# Prevents runaway computation: either a base > 1M squared, or an exponent > 1M,
# both of which would produce astronomically large results and waste CPU cycles.
_MAX_EXPONENT_OPERAND = 1e6

_SAFE_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}

_SAFE_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expression: str) -> float:
    """
    Evaluate a numeric expression safely via AST walk.

    Only numeric constants and arithmetic operators are allowed.
    Exponentiation is checked to prevent runaway computation.
    """
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> float:
    """Walk the AST node tree and compute the numeric result."""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            msg = f"Unsupported constant: {node.value!r}"
            raise TypeError(msg)
        return float(node.value)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_UNARY_OPS:
            msg = f"Unsupported operator: {op_type.__name__}"
            raise ValueError(msg)
        operand = _eval_node(node.operand)
        return _SAFE_UNARY_OPS[op_type](operand)

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)

        if op_type is ast.Pow:
            return _eval_pow(node)

        if op_type not in _SAFE_BIN_OPS:
            msg = f"Unsupported operator: {op_type.__name__}"
            raise ValueError(msg)

        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _SAFE_BIN_OPS[op_type](left, right)

    msg = f"Unsupported expression element: {type(node).__name__}"
    raise ValueError(msg)


def _eval_pow(node: ast.BinOp) -> float:
    """Evaluate power with size guard to prevent DoS."""
    base = _eval_node(node.left)
    exponent = _eval_node(node.right)

    if abs(base) > _MAX_EXPONENT_OPERAND and exponent > 1:
        msg = "Exponentiation too large: base exceeds limit"
        raise ValueError(msg)
    if abs(exponent) > _MAX_EXPONENT_OPERAND:
        msg = "Exponentiation too large: exponent exceeds limit"
        raise ValueError(msg)

    result = base**exponent

    if abs(result) > _MAX_EXPONENT_RESULT:
        msg = "Exponentiation too large: result exceeds limit"
        raise ValueError(msg)
    return result


class CalculatorTool(BaseTool):
    """Tool for performing math operations."""

    name = "calculate"
    description = "Calculator for math operations.\nExpressions support +, -, *, /, %, ** for exponentiation, and parentheses."
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "operation",
                description="The math operation to perform.",
            ): SelectSelector(
                SelectSelectorConfig(
                    options=["expression", "min", "max", "avg"],
                    multiple=False,
                ),
            ),
            vol.Required(
                "data",
                description="The data to evaluate. If using `expression`, pass the entire data in the first item of the array.",
            ): list[str],
        },
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Execute the calculation and return the result."""
        operation = tool_input.tool_args["operation"].lower()
        data = tool_input.tool_args["data"]

        _LOGGER.info("Calculator called: operation=%s, data=%s", operation, data)

        try:
            if operation == "expression":
                result = await hass.async_add_executor_job(_calculate_expression, data)
            else:
                result = _calculate_aggregate(operation, data)
        except Exception as e:
            _LOGGER.exception(msg="Calculator encountered an error")
            return {"error": str(e)}

        return {"value": result}


def _calculate_expression(data: list[str]) -> str:
    """Evaluate an arithmetic expression safely."""
    result = _safe_eval(data[0])

    if result.is_integer():
        result = int(result)
    return str(result)


def _calculate_aggregate(operation: str, data: list[str]) -> float:
    """Perform a min/max/avg aggregation on the supplied data."""
    data_float = [float(num) for num in data]

    if operation == "min":
        return min(data_float)

    if operation == "max":
        return max(data_float)

    if operation == "avg":
        return sum(data_float) / len(data_float)

    error_msg = f"Unknown operation: {operation}"
    raise ValueError(error_msg)
