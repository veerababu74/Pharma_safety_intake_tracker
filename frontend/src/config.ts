const HARDCODED_API_BASE = 'http://127.0.0.1:8000/api/v1';

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || HARDCODED_API_BASE;
