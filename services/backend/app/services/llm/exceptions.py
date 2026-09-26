"""Typed exceptions for LLM Provider interactions and fault classification."""
from __future__ import annotations


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""
    def __init__(self, message: str, error_code: str = "LLM_PROVIDER_ERROR", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.retryable = retryable


class LLMAuthenticationError(LLMProviderError):
    """HTTP 401: Invalid API key or unauthorized. Non-retryable."""
    def __init__(self, message: str = "Lỗi xác thực khóa API nhà cung cấp LLM."):
        super().__init__(message, error_code="AUTHENTICATION_FAILED", retryable=False)


class LLMQuotaExhaustedError(LLMProviderError):
    """HTTP 402: Insufficient balance/quota on provider account. Non-retryable."""
    def __init__(self, message: str = "Số dư tài khoản nhà cung cấp LLM không đủ."):
        super().__init__(message, error_code="QUOTA_EXHAUSTED", retryable=False)


class LLMRateLimitError(LLMProviderError):
    """HTTP 429: Rate limit exceeded. Retryable with backoff."""
    def __init__(self, message: str = "Vượt quá giới hạn tần suất gọi API (Rate limit)."):
        super().__init__(message, error_code="RATE_LIMIT_EXCEEDED", retryable=True)


class LLMModelUnavailableError(LLMProviderError):
    """Model does not exist or is deprecated/unavailable. Non-retryable."""
    def __init__(self, message: str = "Mô hình LLM được yêu cầu không khả dụng hoặc không tồn tại."):
        super().__init__(message, error_code="MODEL_UNAVAILABLE", retryable=False)


class LLMTimeoutError(LLMProviderError):
    """Transport / network timeout. Retryable once with backoff."""
    def __init__(self, message: str = "Hết thời gian chờ phản hồi từ nhà cung cấp LLM (Timeout)."):
        super().__init__(message, error_code="NETWORK_TIMEOUT", retryable=True)


class LLMServerError(LLMProviderError):
    """HTTP 5xx: Provider internal server error. Retryable once with backoff."""
    def __init__(self, message: str = "Máy chủ nhà cung cấp LLM gặp lỗi nội bộ (5xx)."):
        super().__init__(message, error_code="PROVIDER_SERVER_ERROR", retryable=True)


class LLMRefusalError(LLMProviderError):
    """Model refused to answer due to safety / content policy. Non-retryable."""
    def __init__(self, message: str = "Mô hình từ chối xử lý nội dung (Content refusal / safety policy)."):
        super().__init__(message, error_code="CONTENT_REFUSAL", retryable=False)


class LLMTruncatedError(LLMProviderError):
    """Response was cut off due to max output tokens (finish_reason=length)."""
    def __init__(self, message: str = "Phản hồi bị cắt ngang do vượt quá giới hạn token đầu ra (Truncated)."):
        super().__init__(message, error_code="RESPONSE_TRUNCATED", retryable=True)


class LLMEmptyResponseError(LLMProviderError):
    """Model returned an empty content payload."""
    def __init__(self, message: str = "Mô hình trả về phản hồi rỗng (Empty content)."):
        super().__init__(message, error_code="EMPTY_RESPONSE", retryable=True)


class LLMMalformedJSONError(LLMProviderError):
    """Model response could not be parsed as valid JSON."""
    def __init__(self, message: str = "Phản hồi từ mô hình không đúng định dạng JSON hợp lệ."):
        super().__init__(message, error_code="MALFORMED_JSON", retryable=True)


class BudgetExceededError(Exception):
    """Raised when request cost exceeds available budget period limit."""
    pass
