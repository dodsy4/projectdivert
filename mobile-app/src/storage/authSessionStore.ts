import * as SecureStore from 'expo-secure-store';
import type { AuthResponse, UserRole } from '../api/client';

const SESSION_KEY = 'projectdivert-auth-session';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isUserRole(value: unknown): value is UserRole {
  return value === 'customer' || value === 'driver' || value === 'admin';
}

function isAuthResponse(value: unknown): value is AuthResponse {
  if (!isRecord(value)) {
    return false;
  }

  const user = value.user;
  if (!isRecord(user)) {
    return false;
  }

  return (
    typeof value.access_token === 'string' &&
    typeof value.token_type === 'string' &&
    typeof value.expires_in_hours === 'number' &&
    typeof user.id === 'number' &&
    typeof user.email === 'string' &&
    typeof user.name === 'string' &&
    isUserRole(user.role)
  );
}

export async function loadAuthSession(): Promise<AuthResponse | null> {
  const content = await SecureStore.getItemAsync(SESSION_KEY);
  if (!content) {
    return null;
  }

  try {
    const parsed = JSON.parse(content);
    if (isAuthResponse(parsed)) {
      return parsed;
    }
  } catch {
    // If stored data is corrupted, treat it as logged-out state.
  }

  await SecureStore.deleteItemAsync(SESSION_KEY);
  return null;
}

export async function persistAuthSession(auth: AuthResponse): Promise<void> {
  await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(auth));
}

export async function clearAuthSession(): Promise<void> {
  await SecureStore.deleteItemAsync(SESSION_KEY);
}
