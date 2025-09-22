import jmespath
import operator
from typing import Any, Dict

class ConditionEvaluator:
    """
    Safely evaluates string-based conditions against the service state.

    This evaluator avoids using `eval()` by parsing simple binary expressions
    (e.g., 'key == "value"') and using jmespath to query the state.
    """

    OPERATORS = {
        '==': operator.eq,
        '!=': operator.ne,
        '>': operator.gt,
        '<': operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
    }

    def evaluate(self, condition: str, state: Dict[str, Any]) -> bool:
        """
        Evaluates a condition against the given state.

        Args:
            condition: The condition string (e.g., 'user.outcome == "SUCCESS"').
            state: The service state dictionary.

        Returns:
            True if the condition is met, False otherwise.
        """
        for op_str, op_func in self.OPERATORS.items():
            if op_str in condition:
                parts = [p.strip() for p in condition.split(op_str, 1)]
                if len(parts) == 2:
                    key, raw_value = parts
                    
                    # Use jmespath to get the actual value from the state
                    actual_value = jmespath.search(key, state)
                    
                    # Safely evaluate the expected value
                    expected_value = self._parse_value(raw_value)

                    return op_func(actual_value, expected_value)

        # If no operator is found, we can treat it as a truthiness check.
        # A non-empty value or a True boolean should evaluate to True.
        value = jmespath.search(condition, state)
        return bool(value)

    def _parse_value(self, raw_value: str) -> Any:
        """
        Parses the raw string value from the condition into a Python type.
        """
        raw_value = raw_value.strip()
        
        # Handle boolean literals
        if raw_value.lower() == 'true':
            return True
        if raw_value.lower() == 'false':
            return False
        if raw_value.lower() == 'none' or raw_value.lower() == 'null':
            return None

        # Handle string literals (quoted)
        if (raw_value.startswith('"') and raw_value.endswith('"')) or \
           (raw_value.startswith("'") and raw_value.endswith("'")):
            return raw_value[1:-1]

        # Handle numeric literals
        try:
            if '.' in raw_value:
                return float(raw_value)
            return int(raw_value)
        except ValueError:
            # If it's not a recognized type, return it as a plain string
            # This might happen if a value is compared to another key, which we don't support yet.
            # For now, this is a safe default.
            return raw_value

# Example Usage:
if __name__ == '__main__':
    evaluator = ConditionEvaluator()
    test_state = {
        'user': {
            'name': 'John Doe',
            'age': 30,
            'is_verified': True
        },
        'transaction': {
            'amount': 150,
            'outcome': 'SUCCESS'
        },
        'debts_found': True
    }

    print(f"user.age > 25: {evaluator.evaluate('user.age > 25', test_state)}") # True
    print(f"transaction.outcome == 'SUCCESS': {evaluator.evaluate('transaction.outcome == "SUCCESS"', test_state)}") # True
    print(f"user.is_verified == true: {evaluator.evaluate('user.is_verified == true', test_state)}") # True
    print(f"user.name == 'Jane Doe': {evaluator.evaluate('user.name == "Jane Doe"', test_state)}") # False
    print(f"debts_found: {evaluator.evaluate('debts_found', test_state)}") # True
    print(f"transaction.amount <= 100: {evaluator.evaluate('transaction.amount <= 100', test_state)}") # False
