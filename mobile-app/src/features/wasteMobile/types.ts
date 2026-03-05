import type { UpdateStatusPayload } from '../../api/client';

export type RequestFormState = {
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

export type DriverOfferState = {
  requestId: string;
  offerToken: string;
};

export type DriverJobState = {
  requestId: string;
  vehicleId: string;
  latitude: string;
  longitude: string;
};

export type CustomerScreen = 'new-request' | 'request-status';
export type DriverScreen = 'offer-inbox' | 'active-job';
export type AdminViewMode = 'customer' | 'driver';

export type ScreenTab = {
  id: string;
  label: string;
};

export const customerTabs: ScreenTab[] = [
  { id: 'new-request', label: 'New Request' },
  { id: 'request-status', label: 'Request Status' },
];

export const driverTabs: ScreenTab[] = [
  { id: 'offer-inbox', label: 'Offer Inbox' },
  { id: 'active-job', label: 'Active Job' },
];

export const driverProgressionStatuses: UpdateStatusPayload['status'][] = [
  'accepted',
  'en_route',
  'arrived',
  'collected',
  'completed',
];

export const defaultDriverOfferState: DriverOfferState = {
  requestId: '',
  offerToken: '',
};

export const defaultDriverJobState: DriverJobState = {
  requestId: '',
  vehicleId: 'van-42',
  latitude: '',
  longitude: '',
};

export function defaultFormState(): RequestFormState {
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
}
