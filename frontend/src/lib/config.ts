/**
 * API base URL.
 * In production, calls go directly to the backend API.
 * In dev, Vite proxy handles /api/* → localhost:8000.
 */
export const API_BASE = import.meta.env.DEV ? '' : 'https://api.sloptotal.com';
