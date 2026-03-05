import { useCallback, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import type { AuthResponse } from '../../../api/client';
import { apiClient } from '../../../api/client';
import { normalizeError } from './utils';

type UseOsPushNotificationsParams = {
  auth: AuthResponse | null;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  setInfo: React.Dispatch<React.SetStateAction<string | null>>;
};

let foregroundNotificationHandlerConfigured = false;

function optionalRequire(moduleName: string): any | null {
  try {
    const dynamicRequire = (0, eval)('require') as (name: string) => any;
    return dynamicRequire(moduleName);
  } catch {
    return null;
  }
}

function resolveExpoProjectId(constantsModule: any): string | undefined {
  const constants = constantsModule?.default || constantsModule;
  return (
    constants?.expoConfig?.extra?.eas?.projectId ||
    constants?.easConfig?.projectId ||
    undefined
  );
}

export function useOsPushNotifications(params: UseOsPushNotificationsParams) {
  const { auth, setError, setInfo } = params;
  const pushTokenRef = useRef<string | null>(null);

  useEffect(() => {
    if (!auth) {
      return;
    }

    let cancelled = false;

    const setupPush = async () => {
      try {
        const notifications = optionalRequire('expo-notifications');
        const device = optionalRequire('expo-device');
        const constants = optionalRequire('expo-constants');

        if (!notifications || !device) {
          return;
        }

        if (!foregroundNotificationHandlerConfigured && notifications.setNotificationHandler) {
          notifications.setNotificationHandler({
            handleNotification: async () => ({
              shouldShowAlert: true,
              shouldPlaySound: true,
              shouldSetBadge: false,
            }),
          });
          foregroundNotificationHandlerConfigured = true;
        }

        if (device.isDevice === false) {
          return;
        }

        const permissions = await notifications.getPermissionsAsync();
        let status = permissions?.status;
        if (status !== 'granted') {
          const requested = await notifications.requestPermissionsAsync();
          status = requested?.status;
        }

        if (status !== 'granted') {
          return;
        }

        const projectId = resolveExpoProjectId(constants);
        const tokenResponse = projectId
          ? await notifications.getExpoPushTokenAsync({ projectId })
          : await notifications.getExpoPushTokenAsync();

        const expoPushToken = String(tokenResponse?.data || '').trim();
        if (!expoPushToken || cancelled) {
          return;
        }

        pushTokenRef.current = expoPushToken;
        await apiClient.upsertPushSubscription(
          {
            token: expoPushToken,
            provider: 'expo',
            platform: Platform.OS,
          },
          auth.access_token,
        );
        if (!cancelled) {
          setInfo('OS push notifications enabled.');
        }
      } catch (err) {
        if (!cancelled) {
          setError(normalizeError(err));
        }
      }
    };

    setupPush();

    return () => {
      cancelled = true;
    };
  }, [auth, setError, setInfo]);

  const onBeforeLogout = useCallback(async () => {
    if (!auth || !pushTokenRef.current) {
      return;
    }

    try {
      await apiClient.deletePushSubscription(
        {
          token: pushTokenRef.current,
        },
        auth.access_token,
      );
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      pushTokenRef.current = null;
    }
  }, [auth, setError]);

  return {
    onBeforeLogout,
  };
}
