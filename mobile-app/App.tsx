import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Button,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {
  ApiError,
  apiClient,
  CreateWasteRequestResponse,
  WasteRequestDetails,
  AuthResponse,
  UpdateStatusPayload,
} from './src/api/client';

type LoginState = {
  email: string;
  password: string;
};

type RequestFormState = {
  requesterName: string;
  requesterEmail: string;
  materialType: string;
  customMaterialType: string;
  wasteAmount: string;
  wasteUnit: string;
  matchRadiusMiles: string;
  pickupAddress: string;
  pickupCity: string;
  pickupCounty: string;
  pickupPostcode: string;
  scheduledPickupAtLocal: string;
  notes: string;
};

type DriverControlsState = {
  requestId: string;
  status: string;
  latitude: string;
  longitude: string;
  driverId: string;
  vehicleId: string;
};

const defaultFormState = (): RequestFormState => {
  const defaultDate = new Date(Date.now() + 60 * 60 * 1000);
  const isoLocal = new Date(defaultDate.getTime() - defaultDate.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);

  return {
    requesterName: '',
    requesterEmail: '',
    materialType: 'Wood',
    customMaterialType: '',
    wasteAmount: '1',
    wasteUnit: 'Tonnes',
    matchRadiusMiles: '25',
    pickupAddress: '',
    pickupCity: '',
    pickupCounty: '',
    pickupPostcode: '',
    scheduledPickupAtLocal: isoLocal,
    notes: '',
  };
};

const defaultDriverControls: DriverControlsState = {
  requestId: '',
  status: 'en_route',
  latitude: '',
  longitude: '',
  driverId: 'driver-1',
  vehicleId: 'van-42',
};

const allowedStatuses: UpdateStatusPayload['status'][] = [
  'pending_match',
  'matched',
  'accepted',
  'rejected',
  'en_route',
  'arrived',
  'collected',
  'completed',
  'cancelled',
];

function parseStatusValue(value: string): UpdateStatusPayload['status'] | null {
  const normalized = value.trim().toLowerCase();
  if ((allowedStatuses as string[]).includes(normalized)) {
    return normalized as UpdateStatusPayload['status'];
  }
  return null;
}

export default function App() {
  const [login, setLogin] = useState<LoginState>({ email: '', password: '' });
  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [form, setForm] = useState<RequestFormState>(defaultFormState);
  const [created, setCreated] = useState<CreateWasteRequestResponse | null>(null);
  const [requestDetails, setRequestDetails] = useState<WasteRequestDetails | null>(null);
  const [trackedRequestId, setTrackedRequestId] = useState('');
  const [driver, setDriver] = useState<DriverControlsState>(defaultDriverControls);
  const [isLoading, setIsLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const canCreateRequest = auth?.user.role === 'customer' || auth?.user.role === 'admin';
  const canDrive = auth?.user.role === 'driver' || auth?.user.role === 'admin';

  const parsedTrackedRequestId = Number(trackedRequestId);
  const hasTrackedRequest = Number.isInteger(parsedTrackedRequestId) && parsedTrackedRequestId > 0;

  const statusLine = useMemo(() => {
    if (!requestDetails) {
      return 'No request loaded.';
    }
    const status = requestDetails.request.status || 'unknown';
    const provider = requestDetails.match?.provider_name || 'No provider matched yet';
    return `Status: ${status} | Provider: ${provider}`;
  }, [requestDetails]);

  useEffect(() => {
    if (!auth || !hasTrackedRequest) {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      setIsPolling(true);
      try {
        const [details, latest] = await Promise.all([
          apiClient.getWasteRequest(parsedTrackedRequestId, auth.access_token),
          apiClient.getLatestLocation(parsedTrackedRequestId, auth.access_token),
        ]);

        if (cancelled) {
          return;
        }

        if (latest?.latest_location) {
          setRequestDetails({
            ...details,
            latest_location: latest.latest_location,
          });
        } else {
          setRequestDetails(details);
        }
      } catch (err) {
        if (!cancelled) {
          setError(normalizeError(err));
        }
      } finally {
        if (!cancelled) {
          setIsPolling(false);
        }
      }
    };

    poll();
    const timer = setInterval(poll, 10000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [auth, parsedTrackedRequestId, hasTrackedRequest]);

  const onLogin = async () => {
    setError(null);
    setInfo(null);
    setIsLoading(true);
    try {
      const response = await apiClient.login(login.email.trim(), login.password);
      setAuth(response);
      setForm((prev) => ({
        ...prev,
        requesterName: response.user.name || prev.requesterName,
        requesterEmail: response.user.email || prev.requesterEmail,
      }));
      setInfo(`Signed in as ${response.user.email} (${response.user.role}).`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const onCreateRequest = async () => {
    if (!auth) {
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);

    try {
      const schedule = new Date(form.scheduledPickupAtLocal);
      if (Number.isNaN(schedule.getTime())) {
        throw new Error('Scheduled pickup date must be a valid datetime format (YYYY-MM-DDTHH:mm).');
      }

      const response = await apiClient.createWasteRequest(
        {
          requester_name: form.requesterName.trim(),
          requester_email: form.requesterEmail.trim().toLowerCase(),
          material_type: form.materialType.trim(),
          custom_material_type: form.customMaterialType.trim() || undefined,
          waste_amount: Number(form.wasteAmount),
          waste_unit: form.wasteUnit.trim(),
          match_radius_miles: Number(form.matchRadiusMiles),
          pickup_address: form.pickupAddress.trim(),
          pickup_city: form.pickupCity.trim() || undefined,
          pickup_county: form.pickupCounty.trim() || undefined,
          pickup_postcode: form.pickupPostcode.trim(),
          scheduled_pickup_at: schedule.toISOString(),
          notes: form.notes.trim() || undefined,
        },
        auth.access_token,
      );

      setCreated(response);
      setTrackedRequestId(String(response.request.id));
      setDriver((prev) => ({ ...prev, requestId: String(response.request.id) }));
      const details = await apiClient.getWasteRequest(response.request.id, auth.access_token);
      setRequestDetails(details);
      setInfo(`Created waste request #${response.request.id}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const onRefreshNow = async () => {
    if (!auth || !hasTrackedRequest) {
      return;
    }
    setError(null);
    setInfo(null);
    setIsLoading(true);
    try {
      const details = await apiClient.getWasteRequest(parsedTrackedRequestId, auth.access_token);
      setRequestDetails(details);
      setInfo(`Fetched request #${parsedTrackedRequestId}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const onUpdateStatus = async () => {
    if (!auth) {
      return;
    }
    const requestId = Number(driver.requestId);
    if (!Number.isInteger(requestId) || requestId <= 0) {
      setError('Driver request ID must be a positive integer.');
      return;
    }

    const statusValue = parseStatusValue(driver.status);
    if (!statusValue) {
      setError(`Invalid status. Allowed: ${allowedStatuses.join(', ')}`);
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);
    try {
      await apiClient.updateWasteRequestStatus(
        requestId,
        { status: statusValue },
        auth.access_token,
      );
      setTrackedRequestId(String(requestId));
      setInfo(`Updated request #${requestId} to status '${statusValue}'.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const onPushLocation = async () => {
    if (!auth) {
      return;
    }

    const requestId = Number(driver.requestId);
    const latitude = Number(driver.latitude);
    const longitude = Number(driver.longitude);

    if (!Number.isInteger(requestId) || requestId <= 0) {
      setError('Driver request ID must be a positive integer.');
      return;
    }
    if (Number.isNaN(latitude) || Number.isNaN(longitude)) {
      setError('Latitude and longitude must be valid numbers.');
      return;
    }

    setError(null);
    setInfo(null);
    setIsLoading(true);
    try {
      await apiClient.pushVehicleLocation(
        requestId,
        {
          latitude,
          longitude,
          driver_id: driver.driverId.trim() || undefined,
          vehicle_id: driver.vehicleId.trim() || undefined,
          source: 'mobile',
        },
        auth.access_token,
      );
      setTrackedRequestId(String(requestId));
      setInfo(`Sent location update for request #${requestId}.`);
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Project Divert Mobile MVP</Text>
        <Text style={styles.caption}>API Base URL: {apiClient.apiBaseUrl}</Text>

        {!auth ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>1) Login</Text>
            <Field
              label="Email"
              value={login.email}
              onChangeText={(value) => setLogin((prev) => ({ ...prev, email: value }))}
              autoCapitalize="none"
            />
            <Field
              label="Password"
              value={login.password}
              onChangeText={(value) => setLogin((prev) => ({ ...prev, password: value }))}
              secureTextEntry
            />
            <Button title={isLoading ? 'Signing in...' : 'Sign in'} onPress={onLogin} disabled={isLoading} />
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Signed in as {auth.user.email}</Text>
            <Text>Role: {auth.user.role}</Text>
          </View>
        )}

        {auth && canCreateRequest && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>2) Create Waste Request (Customer)</Text>
            <Field label="Requester name" value={form.requesterName} onChangeText={(value) => setForm((prev) => ({ ...prev, requesterName: value }))} />
            <Field label="Requester email" value={form.requesterEmail} onChangeText={(value) => setForm((prev) => ({ ...prev, requesterEmail: value }))} autoCapitalize="none" />
            <Field label="Material type" value={form.materialType} onChangeText={(value) => setForm((prev) => ({ ...prev, materialType: value }))} />
            <Field label="Custom material (if Material type is Other)" value={form.customMaterialType} onChangeText={(value) => setForm((prev) => ({ ...prev, customMaterialType: value }))} />
            <Field label="Waste amount" value={form.wasteAmount} onChangeText={(value) => setForm((prev) => ({ ...prev, wasteAmount: value }))} keyboardType="decimal-pad" />
            <Field label="Waste unit" value={form.wasteUnit} onChangeText={(value) => setForm((prev) => ({ ...prev, wasteUnit: value }))} />
            <Field label="Match radius miles" value={form.matchRadiusMiles} onChangeText={(value) => setForm((prev) => ({ ...prev, matchRadiusMiles: value }))} keyboardType="decimal-pad" />
            <Field label="Pickup address" value={form.pickupAddress} onChangeText={(value) => setForm((prev) => ({ ...prev, pickupAddress: value }))} />
            <Field label="Pickup city" value={form.pickupCity} onChangeText={(value) => setForm((prev) => ({ ...prev, pickupCity: value }))} />
            <Field label="Pickup county" value={form.pickupCounty} onChangeText={(value) => setForm((prev) => ({ ...prev, pickupCounty: value }))} />
            <Field label="Pickup postcode" value={form.pickupPostcode} onChangeText={(value) => setForm((prev) => ({ ...prev, pickupPostcode: value }))} autoCapitalize="characters" />
            <Field label="Scheduled pickup (local)" value={form.scheduledPickupAtLocal} onChangeText={(value) => setForm((prev) => ({ ...prev, scheduledPickupAtLocal: value }))} placeholder="YYYY-MM-DDTHH:mm" />
            <Field label="Notes" value={form.notes} onChangeText={(value) => setForm((prev) => ({ ...prev, notes: value }))} multiline />

            <Button
              title={isLoading ? 'Submitting...' : 'Submit request'}
              onPress={onCreateRequest}
              disabled={isLoading}
            />
          </View>
        )}

        {auth && canDrive && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>3) Driver Controls (Simulation)</Text>
            <Field label="Request ID" value={driver.requestId} onChangeText={(value) => setDriver((prev) => ({ ...prev, requestId: value }))} keyboardType="number-pad" />
            <Field label="Status" value={driver.status} onChangeText={(value) => setDriver((prev) => ({ ...prev, status: value }))} placeholder="en_route" />
            <Button title={isLoading ? 'Updating...' : 'Update status'} onPress={onUpdateStatus} disabled={isLoading} />

            <Field label="Latitude" value={driver.latitude} onChangeText={(value) => setDriver((prev) => ({ ...prev, latitude: value }))} keyboardType="decimal-pad" />
            <Field label="Longitude" value={driver.longitude} onChangeText={(value) => setDriver((prev) => ({ ...prev, longitude: value }))} keyboardType="decimal-pad" />
            <Field label="Driver ID" value={driver.driverId} onChangeText={(value) => setDriver((prev) => ({ ...prev, driverId: value }))} />
            <Field label="Vehicle ID" value={driver.vehicleId} onChangeText={(value) => setDriver((prev) => ({ ...prev, vehicleId: value }))} />
            <Button title={isLoading ? 'Sending...' : 'Push location'} onPress={onPushLocation} disabled={isLoading} />
          </View>
        )}

        {auth && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>4) Track Request</Text>
            <Field label="Tracked request ID" value={trackedRequestId} onChangeText={setTrackedRequestId} keyboardType="number-pad" />
            <Button title={isLoading ? 'Refreshing...' : 'Refresh now'} onPress={onRefreshNow} disabled={isLoading || !hasTrackedRequest} />
            <View style={styles.pollRow}>
              {isPolling ? <ActivityIndicator size="small" /> : null}
              <Text>{hasTrackedRequest ? 'Auto-refresh every 10s' : 'Enter request ID to start polling'}</Text>
            </View>
          </View>
        )}

        {created && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Latest Created Request</Text>
            <Text>Request ID: {created.request.id}</Text>
            <Text>{statusLine}</Text>
            {created.match ? <Text>Matched distance: {created.match.distance_miles} miles</Text> : null}
            {created.drive_time ? (
              <Text>
                Drive time: {created.drive_time.duration_text || 'n/a'} ({created.drive_time.distance_text || 'n/a'})
              </Text>
            ) : (
              <Text>Drive time: unavailable</Text>
            )}
            {requestDetails?.latest_location ? (
              <Text>
                Latest location: {requestDetails.latest_location.latitude}, {requestDetails.latest_location.longitude}
              </Text>
            ) : (
              <Text>Latest location: none yet</Text>
            )}
          </View>
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

type FieldProps = {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  keyboardType?: 'default' | 'decimal-pad' | 'number-pad' | 'email-address';
  autoCapitalize?: 'none' | 'sentences' | 'words' | 'characters';
  secureTextEntry?: boolean;
  multiline?: boolean;
};

function Field(props: FieldProps) {
  const {
    label,
    value,
    onChangeText,
    placeholder,
    keyboardType,
    autoCapitalize,
    secureTextEntry,
    multiline,
  } = props;

  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        style={[styles.input, multiline ? styles.inputMultiline : undefined]}
        placeholder={placeholder}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize || 'sentences'}
        secureTextEntry={secureTextEntry}
        multiline={multiline}
      />
    </View>
  );
}

function normalizeError(err: unknown): string {
  if (err instanceof ApiError) {
    return `${err.message} (HTTP ${err.status})`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return 'Unexpected error';
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#f7f7f7',
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
  field: {
    gap: 4,
  },
  fieldLabel: {
    fontSize: 12,
    fontWeight: '600',
  },
  input: {
    borderWidth: 1,
    borderColor: '#cfcfcf',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    backgroundColor: '#fff',
  },
  inputMultiline: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  pollRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 8,
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
