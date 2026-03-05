import { useCallback, useEffect, useState } from 'react';
import { apiClient, type AuthResponse, type SignupResponse } from '../../../api/client';
import {
  clearAuthSession,
  loadAuthSession,
  persistAuthSession,
} from '../../../storage/authSessionStore';
import type { RequestFormState } from '../types';
import {
  defaultLoginState,
  defaultPasswordResetConfirmState,
  defaultPasswordResetRequestState,
  defaultSignupState,
  defaultVerifyConfirmState,
  defaultVerifyRequestState,
  mergeRequesterDetails,
  normalizeError,
  type AuthScreen,
  type LoginState,
  type PasswordResetConfirmState,
  type PasswordResetRequestState,
  type SignupState,
  type VerifyConfirmState,
  type VerifyRequestState,
} from './utils';

type UseAuthSessionParams = {
  setForm: React.Dispatch<React.SetStateAction<RequestFormState>>;
  setInfo: React.Dispatch<React.SetStateAction<string | null>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
};

export function useAuthSession(params: UseAuthSessionParams) {
  const { setForm, setInfo, setError, setIsLoading } = params;

  const [authScreen, setAuthScreen] = useState<AuthScreen>('sign-in');
  const [login, setLogin] = useState<LoginState>(defaultLoginState);
  const [signup, setSignup] = useState<SignupState>(defaultSignupState);
  const [verifyRequest, setVerifyRequest] = useState<VerifyRequestState>(defaultVerifyRequestState);
  const [verifyConfirm, setVerifyConfirm] = useState<VerifyConfirmState>(defaultVerifyConfirmState);
  const [passwordResetRequest, setPasswordResetRequest] = useState<PasswordResetRequestState>(
    defaultPasswordResetRequestState,
  );
  const [passwordResetConfirm, setPasswordResetConfirm] = useState<PasswordResetConfirmState>(
    defaultPasswordResetConfirmState,
  );
  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [isBootstrappingSession, setIsBootstrappingSession] = useState(true);

  const applySignedInSession = useCallback(
    async (response: AuthResponse, successMessage: string) => {
      setAuth(response);
      setForm((prev) => mergeRequesterDetails(prev, response));

      try {
        await persistAuthSession(response);
        setInfo(successMessage);
      } catch (persistError) {
        setInfo(`${successMessage} Session persistence failed: ${normalizeError(persistError)}`);
      }
    },
    [setForm, setInfo],
  );

  const clearSession = useCallback(async () => {
    try {
      await clearAuthSession();
    } catch {
      // Best effort clear; continue resetting in-memory session.
    }

    setAuth(null);
  }, []);

  useEffect(() => {
    apiClient.configureAuthLifecycle({
      getAuth: () => auth,
      onAuthRefreshed: async (nextAuth) => {
        setAuth(nextAuth);
        setForm((prev) => mergeRequesterDetails(prev, nextAuth));
        try {
          await persistAuthSession(nextAuth);
        } catch {
          // Keep session in memory even if persistence fails.
        }
      },
      onAuthInvalid: async () => {
        await clearSession();
        setAuthScreen('sign-in');
        setInfo('Session expired. Please sign in again.');
      },
    });

    return () => {
      apiClient.configureAuthLifecycle(null);
    };
  }, [auth, clearSession, setForm, setInfo]);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      try {
        const restored = await loadAuthSession();
        if (cancelled || !restored) {
          return;
        }

        setAuth(restored);
        setForm((prev) => mergeRequesterDetails(prev, restored));
        setInfo(`Restored session for ${restored.user.email}.`);
      } catch (err) {
        if (!cancelled) {
          setError(normalizeError(err));
        }
      } finally {
        if (!cancelled) {
          setIsBootstrappingSession(false);
        }
      }
    };

    bootstrap();

    return () => {
      cancelled = true;
    };
  }, [setError, setForm, setInfo]);

  const onLogin = useCallback(async () => {
    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const response = await apiClient.login(login.email.trim(), login.password);
      setLogin(defaultLoginState);
      await applySignedInSession(response, `Signed in as ${response.user.email} (${response.user.role}).`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [applySignedInSession, login.email, login.password, setError, setInfo, setIsLoading]);

  const onSignup = useCallback(async () => {
    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const response = await apiClient.signup({
        name: signup.name.trim(),
        email: signup.email.trim().toLowerCase(),
        password: signup.password,
      });
      setSignup(defaultSignupState);

      if ('access_token' in response) {
        await applySignedInSession(
          response as AuthResponse,
          `Account created and signed in as ${(response as AuthResponse).user.email}.`,
        );
        return;
      }

      const pending = response as Exclude<SignupResponse, AuthResponse>;
      const verificationHint = pending.verification_token
        ? ` Verification token: ${pending.verification_token}`
        : '';
      const emailHint = pending.verification_email_sent ? ' Check your email for the verification token.' : '';
      setVerifyRequest({ email: pending.user.email });
      setAuthScreen('verify-confirm');
      setInfo(`Account created for ${pending.user.email}. Verification is required.${emailHint}${verificationHint}`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [applySignedInSession, setError, setInfo, setIsLoading, signup.email, signup.name, signup.password]);

  const onRequestEmailVerification = useCallback(async () => {
    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const response = await apiClient.requestEmailVerification(verifyRequest.email.trim().toLowerCase());
      const tokenHint = response.verification_token ? ` Verification token: ${response.verification_token}` : '';
      setVerifyConfirm((prev) => ({
        ...prev,
        token: response.verification_token || prev.token,
      }));
      setAuthScreen('verify-confirm');
      setInfo(`${response.message}${tokenHint}`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [setError, setInfo, setIsLoading, verifyRequest.email]);

  const onConfirmEmailVerification = useCallback(async () => {
    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const response = await apiClient.confirmEmailVerification(verifyConfirm.token.trim());
      setVerifyConfirm(defaultVerifyConfirmState);
      await applySignedInSession(response, `Email verified and signed in as ${response.user.email}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [applySignedInSession, setError, setInfo, setIsLoading, verifyConfirm.token]);

  const onRequestPasswordReset = useCallback(async () => {
    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const response = await apiClient.requestPasswordReset(
        passwordResetRequest.email.trim().toLowerCase(),
      );
      const tokenHint = response.reset_token ? ` Reset token: ${response.reset_token}` : '';
      setPasswordResetConfirm((prev) => ({
        ...prev,
        token: response.reset_token || prev.token,
      }));
      setAuthScreen('reset-confirm');
      setInfo(`${response.message}${tokenHint}`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [passwordResetRequest.email, setError, setInfo, setIsLoading]);

  const onConfirmPasswordReset = useCallback(async () => {
    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const response = await apiClient.confirmPasswordReset(
        passwordResetConfirm.token.trim(),
        passwordResetConfirm.newPassword,
      );
      setPasswordResetConfirm(defaultPasswordResetConfirmState);
      await applySignedInSession(response, `Password reset complete. Signed in as ${response.user.email}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  }, [applySignedInSession, passwordResetConfirm.newPassword, passwordResetConfirm.token, setError, setInfo, setIsLoading]);

  const onLogout = useCallback(async () => {
    setError(null);
    setInfo(null);

    if (auth?.refresh_token) {
      try {
        await apiClient.logout(auth.refresh_token, auth.access_token);
      } catch {
        // Local sign-out should still proceed even if revoke fails.
      }
    }

    await clearSession();
    setAuthScreen('sign-in');
    setLogin(defaultLoginState);
    setSignup(defaultSignupState);
    setVerifyRequest(defaultVerifyRequestState);
    setVerifyConfirm(defaultVerifyConfirmState);
    setPasswordResetRequest(defaultPasswordResetRequestState);
    setPasswordResetConfirm(defaultPasswordResetConfirmState);
  }, [auth, clearSession, setError, setInfo]);

  return {
    authScreen,
    setAuthScreen,
    login,
    setLogin,
    signup,
    setSignup,
    verifyRequest,
    setVerifyRequest,
    verifyConfirm,
    setVerifyConfirm,
    passwordResetRequest,
    setPasswordResetRequest,
    passwordResetConfirm,
    setPasswordResetConfirm,
    auth,
    isBootstrappingSession,
    onLogin,
    onSignup,
    onRequestEmailVerification,
    onConfirmEmailVerification,
    onRequestPasswordReset,
    onConfirmPasswordReset,
    onLogout,
  };
}
