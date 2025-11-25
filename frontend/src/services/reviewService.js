const DEFAULT_BASE_URL = 'http://localhost:8000';

const resolveBaseUrl = () => {
  const fromEnv = import.meta.env?.VITE_API_BASE_URL;
  if (fromEnv && typeof fromEnv === 'string' && fromEnv.trim()) {
    return fromEnv.trim().replace(/\/+$/, '');
  }

  return DEFAULT_BASE_URL;
};

const API_BASE_URL = resolveBaseUrl();

export async function submitReview(payload) {
  const response = await fetch(`${API_BASE_URL}/api/review`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const errorBody = await response.json();
      if (errorBody?.detail) {
        message = Array.isArray(errorBody.detail)
          ? errorBody.detail.map((item) => item.msg || item).join(', ')
          : errorBody.detail;
      }
    } catch (err) {
      /* response is not JSON, fall back to default message */
    }

    throw new Error(message);
  }

  return response.json();
}
