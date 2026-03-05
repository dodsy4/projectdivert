import React from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import { Field } from '../../components/Field';
import type { DriverOfferState } from '../../features/wasteMobile/types';

type OfferInboxScreenProps = {
  driverOffer: DriverOfferState;
  setDriverOffer: React.Dispatch<React.SetStateAction<DriverOfferState>>;
  isLoading: boolean;
  onAcceptDispatchOffer: () => void;
};

export function OfferInboxScreen(props: OfferInboxScreenProps) {
  const { driverOffer, setDriverOffer, isLoading, onAcceptDispatchOffer } = props;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Offer Inbox</Text>
      <Text style={styles.helperText}>
        Accept jobs using the request ID and offer token sent to the provider.
      </Text>
      <Field
        label="Request ID"
        value={driverOffer.requestId}
        onChangeText={(value) => setDriverOffer((prev) => ({ ...prev, requestId: value }))}
        keyboardType="number-pad"
      />
      <Field
        label="Offer token"
        value={driverOffer.offerToken}
        onChangeText={(value) => setDriverOffer((prev) => ({ ...prev, offerToken: value }))}
        autoCapitalize="none"
      />
      <Button
        title={isLoading ? 'Accepting...' : 'Accept offer'}
        onPress={onAcceptDispatchOffer}
        disabled={isLoading}
      />
    </View>
  );
}

const styles = StyleSheet.create({
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
  helperText: {
    color: '#4a4a4a',
    fontSize: 12,
  },
});
