"""
Interface for direct interactions with the llm library, independent of vibectl config.
"""

import logging

import llm

logger = logging.getLogger(__name__)


def is_valid_llm_model_name(model_name: str) -> tuple[bool, str | None]:
    """Validate if the model name is recognized by the llm library.

    This check attempts to retrieve the model class without validating API keys.

    Args:
        model_name: The name of the model to validate.

    Returns:
        tuple[bool, str | None]: (True, None) if the name is valid,
                                 (False, error_message) if invalid.
    """
    try:
        logger.debug("Validating model name existence via llm: '%s'", model_name)
        # Attempt to get the model class/instance. This might still fail for
        # reasons other than the name being invalid (e.g., some plugins might
        # require initialization), but it's the best check we have without keys.
        llm.get_model(model_name)
        logger.debug("Model name '%s' is recognized by llm.", model_name)
        return True, None
    except Exception as e:
        # Check if the error suggests an unknown model
        error_str = str(e).lower()
        # Use common phrases indicating the model name itself is the problem
        if (
            "unknown model" in error_str
            or "not found" in error_str
            or "invalid model id" in error_str
        ):
            msg = (
                f"Model name '{model_name}' is not recognized by the "
                f"underlying 'llm' library. See 'llm models --known' for "
                f"available options."
            )
            logger.warning(msg)
            return False, msg
        else:
            # Assume the name is potentially valid if the error is different
            # (e.g., key error, connection error). Log for debugging.
            logger.debug(
                "Encountered non-name-related error during llm model name "
                "validation for '%s': %s",
                model_name,
                e,
            )
            # Treat as valid for the purpose of name checking, subsequent key
            # checks will catch other issues.
            return True, None
