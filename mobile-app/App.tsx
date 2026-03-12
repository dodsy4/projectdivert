import React from 'react';
import {
  ActivityIndicator,
  Button,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { apiClient } from './src/api/client';
import { AdminComplianceReviewCard } from './src/components/AdminComplianceReviewCard';
import { AdminDriverEligibilityCard } from './src/components/AdminDriverEligibilityCard';
import { AdminLaunchBillingCard } from './src/components/AdminLaunchBillingCard';
import { Field } from './src/components/Field';
import { ScreenTabs } from './src/components/ScreenTabs';
import {
  customerTabs,
  driverProgressionStatuses,
  driverTabs,
} from './src/features/wasteMobile/types';
import { useWasteMobileController } from './src/features/wasteMobile/hooks/useWasteMobileController';
import { NewRequestScreen } from './src/screens/customer/NewRequestScreen';
import { RequestStatusScreen } from './src/screens/customer/RequestStatusScreen';
import { ActiveJobScreen } from './src/screens/driver/ActiveJobScreen';
import { OfferInboxScreen } from './src/screens/driver/OfferInboxScreen';

const adminModes = ['customer', 'driver'] as const;
const authTabs = [
  { id: 'sign-in', label: 'Sign In' },
  { id: 'sign-up', label: 'Sign Up' },
  { id: 'verify-request', label: 'Verify Request' },
  { id: 'verify-confirm', label: 'Verify Confirm' },
  { id: 'reset-request', label: 'Reset Request' },
  { id: 'reset-confirm', label: 'Reset Confirm' },
];

export default function App() {
  const {
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
    form,
    setForm,
    customerRequestId,
    setCustomerRequestId,
    driverOffer,
    setDriverOffer,
    driverJob,
    setDriverJob,
    complianceUpload,
    setComplianceUpload,
    created,
    customerScreen,
    onSelectCustomerScreen,
    driverScreen,
    onSelectDriverScreen,
    adminViewMode,
    setAdminViewMode,
    isLoading,
    isPolling,
    isRealtimeConnected,
    isFallbackPolling,
    syncState,
    isBootstrappingSession,
    isComplianceQueueLoading,
    isAdminDriversLoading,
    isDriverComplianceLoading,
    info,
    error,
    hasTrackedCustomerRequest,
    customerRelevantRequestDetails,
    driverRelevantRequestDetails,
    adminComplianceReviewQueue,
    adminDrivers,
    driverOwnCompliance,
    currentRole,
    onLogin,
    onSignup,
    onRequestEmailVerification,
    onConfirmEmailVerification,
    onRequestPasswordReset,
    onConfirmPasswordReset,
    onLogout,
    onCreateRequest,
    onRefreshNow,
    onAcceptDispatchOffer,
    onLoadDriverJob,
    onUpdateDriverStatus,
    onPushLocation,
    onUploadComplianceDocument,
    onLoadComplianceReviewQueue,
    onLoadAdminDrivers,
    onLoadDriverOwnCompliance,
    onReviewComplianceDocument,
    onUpdateBillingWorkflow,
  } = useWasteMobileController();

  if (isBootstrappingSession) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loadingScreen}>
          <ActivityIndicator size="large" />
          <Text>Restoring session...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Project Divert Mobile</Text>
        <Text style={styles.caption}>API Base URL: {apiClient.apiBaseUrl}</Text>
        <Text style={styles.caption}>
          Billing mode: {apiClient.paymentsEnabled ? 'In-app payments' : 'Offline invoicing launch mode'}
        </Text>
        <Text style={styles.caption}>
          Realtime: {syncState.replace('_', ' ')} | Reconnect: {apiClient.realtimeReconnectDelayMs}ms
        </Text>

        {!auth ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Account Access</Text>
            <ScreenTabs
              items={authTabs}
              activeId={authScreen}
              onPress={(id) => setAuthScreen(id as typeof authScreen)}
            />

            {authScreen === 'sign-in' ? (
              <>
                <Field
                  label="Email"
                  value={login.email}
                  onChangeText={(value) => setLogin((prev) => ({ ...prev, email: value }))}
                  autoCapitalize="none"
                  keyboardType="email-address"
                />
                <Field
                  label="Password"
                  value={login.password}
                  onChangeText={(value) => setLogin((prev) => ({ ...prev, password: value }))}
                  secureTextEntry
                />
                <Button
                  title={isLoading ? 'Signing in...' : 'Sign in'}
                  onPress={onLogin}
                  disabled={isLoading}
                />
              </>
            ) : null}

            {authScreen === 'sign-up' ? (
              <>
                <Field
                  label="Name"
                  value={signup.name}
                  onChangeText={(value) => setSignup((prev) => ({ ...prev, name: value }))}
                />
                <Field
                  label="Email"
                  value={signup.email}
                  onChangeText={(value) => setSignup((prev) => ({ ...prev, email: value }))}
                  autoCapitalize="none"
                  keyboardType="email-address"
                />
                <Field
                  label="Password"
                  value={signup.password}
                  onChangeText={(value) => setSignup((prev) => ({ ...prev, password: value }))}
                  secureTextEntry
                />
                <Button
                  title={isLoading ? 'Creating account...' : 'Create account'}
                  onPress={onSignup}
                  disabled={isLoading}
                />
              </>
            ) : null}

            {authScreen === 'verify-request' ? (
              <>
                <Text style={styles.helperText}>
                  Request a new email verification token for an existing account.
                </Text>
                <Field
                  label="Email"
                  value={verifyRequest.email}
                  onChangeText={(value) => setVerifyRequest((prev) => ({ ...prev, email: value }))}
                  autoCapitalize="none"
                  keyboardType="email-address"
                />
                <Button
                  title={isLoading ? 'Requesting...' : 'Request verification'}
                  onPress={onRequestEmailVerification}
                  disabled={isLoading}
                />
              </>
            ) : null}

            {authScreen === 'verify-confirm' ? (
              <>
                <Text style={styles.helperText}>
                  Paste the verification token from your email.
                </Text>
                <Field
                  label="Verification Token"
                  value={verifyConfirm.token}
                  onChangeText={(value) => setVerifyConfirm((prev) => ({ ...prev, token: value }))}
                  autoCapitalize="none"
                />
                <Button
                  title={isLoading ? 'Verifying...' : 'Verify and sign in'}
                  onPress={onConfirmEmailVerification}
                  disabled={isLoading}
                />
              </>
            ) : null}

            {authScreen === 'reset-request' ? (
              <>
                <Text style={styles.helperText}>
                  Request a password reset token for your account.
                </Text>
                <Field
                  label="Email"
                  value={passwordResetRequest.email}
                  onChangeText={(value) =>
                    setPasswordResetRequest((prev) => ({ ...prev, email: value }))
                  }
                  autoCapitalize="none"
                  keyboardType="email-address"
                />
                <Button
                  title={isLoading ? 'Requesting...' : 'Request reset token'}
                  onPress={onRequestPasswordReset}
                  disabled={isLoading}
                />
              </>
            ) : null}

            {authScreen === 'reset-confirm' ? (
              <>
                <Text style={styles.helperText}>
                  Paste the reset token and set a new password.
                </Text>
                <Field
                  label="Reset Token"
                  value={passwordResetConfirm.token}
                  onChangeText={(value) =>
                    setPasswordResetConfirm((prev) => ({ ...prev, token: value }))
                  }
                  autoCapitalize="none"
                />
                <Field
                  label="New Password"
                  value={passwordResetConfirm.newPassword}
                  onChangeText={(value) =>
                    setPasswordResetConfirm((prev) => ({ ...prev, newPassword: value }))
                  }
                  secureTextEntry
                />
                <Button
                  title={isLoading ? 'Resetting...' : 'Reset password and sign in'}
                  onPress={onConfirmPasswordReset}
                  disabled={isLoading}
                />
              </>
            ) : null}
          </View>
        ) : (
          <>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Signed in as {auth.user.email}</Text>
              <Text>Role: {auth.user.role}</Text>
            </View>

            {currentRole === 'admin' ? (
              <>
                <View style={styles.card}>
                  <Text style={styles.cardTitle}>Admin View Mode</Text>
                  <View style={styles.modeSwitchRow}>
                    {adminModes.map((mode) => {
                      const selected = adminViewMode === mode;
                      return (
                        <Pressable
                          key={mode}
                          onPress={() => setAdminViewMode(mode)}
                          style={[
                            styles.modeButton,
                            selected ? styles.modeButtonSelected : undefined,
                          ]}
                        >
                          <Text
                            style={[
                              styles.modeButtonText,
                              selected ? styles.modeButtonTextSelected : undefined,
                            ]}
                          >
                            {mode}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </View>
                <AdminComplianceReviewCard
                  queue={adminComplianceReviewQueue}
                  isLoading={isComplianceQueueLoading}
                  onRefresh={onLoadComplianceReviewQueue}
                  onReview={onReviewComplianceDocument}
                />
                <AdminLaunchBillingCard />
                <AdminDriverEligibilityCard
                  drivers={adminDrivers}
                  isLoading={isAdminDriversLoading}
                  onRefresh={onLoadAdminDrivers}
                />
              </>
            ) : null}

            {(currentRole === 'customer' ||
              (currentRole === 'admin' && adminViewMode === 'customer')) && (
              <>
                <ScreenTabs
                  items={customerTabs}
                  activeId={customerScreen}
                  onPress={onSelectCustomerScreen}
                />

                {customerScreen === 'new-request' ? (
                  <NewRequestScreen
                    form={form}
                    setForm={setForm}
                    isLoading={isLoading}
                    onCreateRequest={onCreateRequest}
                  />
                ) : (
                  <RequestStatusScreen
                    customerRequestId={customerRequestId}
                    setCustomerRequestId={setCustomerRequestId}
                    onRefreshNow={onRefreshNow}
                    isLoading={isLoading}
                    hasTrackedRequest={hasTrackedCustomerRequest}
                    isPolling={isPolling}
                    isRealtimeConnected={isRealtimeConnected}
                    isFallbackPolling={isFallbackPolling}
                    created={created}
                    relevantRequestDetails={customerRelevantRequestDetails}
                    audience={currentRole === 'admin' ? 'admin' : 'customer'}
                    onUpdateBillingWorkflow={onUpdateBillingWorkflow}
                  />
                )}
              </>
            )}

            {(currentRole === 'driver' || (currentRole === 'admin' && adminViewMode === 'driver')) && (
              <>
                <ScreenTabs
                  items={driverTabs}
                  activeId={driverScreen}
                  onPress={onSelectDriverScreen}
                />

                {driverScreen === 'offer-inbox' ? (
                  <OfferInboxScreen
                    driverOffer={driverOffer}
                    setDriverOffer={setDriverOffer}
                    isLoading={isLoading}
                    onAcceptDispatchOffer={onAcceptDispatchOffer}
                  />
                ) : (
                  <ActiveJobScreen
                    driverJob={driverJob}
                    setDriverJob={setDriverJob}
                    isLoading={isLoading}
                    onLoadDriverJob={onLoadDriverJob}
                    onUpdateDriverStatus={onUpdateDriverStatus}
                    onPushLocation={onPushLocation}
                    complianceUpload={complianceUpload}
                    setComplianceUpload={setComplianceUpload}
                    onUploadComplianceDocument={onUploadComplianceDocument}
                    statuses={driverProgressionStatuses}
                    relevantRequestDetails={driverRelevantRequestDetails}
                    driverOwnCompliance={driverOwnCompliance}
                    isDriverComplianceLoading={isDriverComplianceLoading}
                    onRefreshDriverOwnCompliance={onLoadDriverOwnCompliance}
                  />
                )}
              </>
            )}

            <View style={styles.card}>
              <Text style={styles.cardTitle}>Account</Text>
              <Text>Email: {auth.user.email}</Text>
              <Text>Role: {auth.user.role}</Text>
              <Text>User ID: {auth.user.id}</Text>
              <Button title="Sign out" onPress={onLogout} disabled={isLoading} />
            </View>
          </>
        )}

        {info ? (
          <View style={styles.infoBox}>
            <Text style={styles.infoText}>{info}</Text>
          </View>
        ) : null}

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#f7f7f7',
  },
  loadingScreen: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
  },
  container: {
    padding: 16,
    gap: 12,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
  },
  caption: {
    fontSize: 12,
    color: '#4d4d4d',
  },
  helperText: {
    fontSize: 12,
    color: '#555555',
  },
  card: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#d8d8d8',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 8,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  modeSwitchRow: {
    flexDirection: 'row',
    gap: 8,
  },
  modeButton: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#cccccc',
    backgroundColor: '#efefef',
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  modeButtonSelected: {
    borderColor: '#1e4f9f',
    backgroundColor: '#dfeaff',
  },
  modeButtonText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#2f2f2f',
    textTransform: 'capitalize',
  },
  modeButtonTextSelected: {
    color: '#123b74',
  },
  infoBox: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#9ac2f7',
    backgroundColor: '#ecf4ff',
    padding: 10,
  },
  infoText: {
    color: '#123b74',
    fontWeight: '600',
  },
  errorBox: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#f2a0a0',
    backgroundColor: '#fff3f3',
    padding: 10,
  },
  errorText: {
    color: '#7a2020',
    fontWeight: '600',
  },
});
