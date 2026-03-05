import { ApiError, type AuthResponse } from '../../../api/client';
import type { RequestFormState } from '../types';

export type LoginState = {
  email: string;
  password: string;
};

export type SignupState = {
  name: string;
  email: string;
  password: string;
};

export type VerifyRequestState = {
  email: string;
};

export type VerifyConfirmState = {
  token: string;
};

export type PasswordResetRequestState = {
  email: string;
};

export type PasswordResetConfirmState = {
  token: string;
  newPassword: string;
};

export type AuthScreen =
  | 'sign-in'
  | 'sign-up'
  | 'verify-request'
  | 'verify-confirm'
  | 'reset-request'
  | 'reset-confirm';

export const defaultLoginState: LoginState = {
  email: '',
  password: '',
};

export const defaultSignupState: SignupState = {
  name: '',
  email: '',
  password: '',
};

export const defaultVerifyRequestState: VerifyRequestState = {
  email: '',
};

export const defaultVerifyConfirmState: VerifyConfirmState = {
  token: '',
};

export const defaultPasswordResetRequestState: PasswordResetRequestState = {
  email: '',
};

export const defaultPasswordResetConfirmState: PasswordResetConfirmState = {
  token: '',
  newPassword: '',
};

export function parsePositiveInt(value: string): number | null {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

export function normalizeError(err: unknown): string {
  if (err instanceof ApiError) {
    return `${err.message} (HTTP ${err.status})`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return 'Unexpected error';
}

export function mergeRequesterDetails(form: RequestFormState, auth: AuthResponse): RequestFormState {
  return {
    ...form,
    requesterName: auth.user.name || form.requesterName,
    requesterEmail: auth.user.email || form.requesterEmail,
  };
}
