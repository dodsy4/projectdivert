import React, { useState } from 'react';
import { Button, Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import type {
  CommunicationTemplate,
  RequestCommunicationChannel,
  RequestCommunicationDirection,
  WasteRequestDetails,
} from '../api/client';
import { Field } from './Field';

const directions: RequestCommunicationDirection[] = ['outbound', 'inbound', 'internal'];
const channels: RequestCommunicationChannel[] = ['email', 'phone', 'sms', 'manual', 'other'];

type AdminCommunicationLogCardProps = {
  details: WasteRequestDetails | null;
  templates?: CommunicationTemplate[] | null;
  isLoading: boolean;
  onSave: (
    requestId: number,
    payload: {
      direction: string;
      channel: string;
      subject?: string;
      message: string;
      outcome?: string;
      contact_name?: string;
      contact_email?: string;
      contact_phone?: string;
      customer_visible?: boolean;
    },
  ) => void;
};

function formatLabel(value: string) {
  return value.replace(/_/g, ' ');
}

export function AdminCommunicationLogCard(props: AdminCommunicationLogCardProps) {
  const { details, templates, isLoading, onSave } = props;
  const [direction, setDirection] = useState<RequestCommunicationDirection>('outbound');
  const [channel, setChannel] = useState<RequestCommunicationChannel>('email');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [outcome, setOutcome] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [customerVisible, setCustomerVisible] = useState(true);

  if (!details) {
    return null;
  }

  const applyTemplate = (template: CommunicationTemplate) => {
    setDirection(template.direction as RequestCommunicationDirection);
    setChannel(template.channel as RequestCommunicationChannel);
    setSubject(template.subject || '');
    setMessage(template.message || '');
    setOutcome(template.outcome || '');
    setCustomerVisible(Boolean(template.customer_visible));
  };

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Admin Communication Log</Text>
      <Text>Request #{details.request.id}</Text>

      {templates?.length ? (
        <View style={styles.templateBlock}>
          <Text style={styles.sectionLabel}>Templates</Text>
          <View style={styles.rowWrap}>
            {templates.map((template) => (
              <Pressable
                key={template.key}
                style={styles.templateChip}
                onPress={() => applyTemplate(template)}
                disabled={isLoading}
              >
                <Text style={styles.templateChipText}>{template.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      <View style={styles.rowWrap}>
        {directions.map((option) => {
          const selected = direction === option;
          return (
            <Pressable
              key={option}
              style={[styles.chip, selected ? styles.chipSelected : undefined]}
              onPress={() => setDirection(option)}
              disabled={isLoading}
            >
              <Text style={selected ? styles.chipTextSelected : styles.chipText}>
                {formatLabel(option)}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.rowWrap}>
        {channels.map((option) => {
          const selected = channel === option;
          return (
            <Pressable
              key={option}
              style={[styles.chip, selected ? styles.chipSelected : undefined]}
              onPress={() => setChannel(option)}
              disabled={isLoading}
            >
              <Text style={selected ? styles.chipTextSelected : styles.chipText}>
                {formatLabel(option)}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Field label="Subject" value={subject} onChangeText={setSubject} />
      <Field label="Message" value={message} onChangeText={setMessage} multiline />
      <Field label="Outcome" value={outcome} onChangeText={setOutcome} />
      <Field label="Contact name" value={contactName} onChangeText={setContactName} />
      <Field
        label="Contact email"
        value={contactEmail}
        onChangeText={setContactEmail}
        autoCapitalize="none"
        keyboardType="email-address"
      />
      <Field label="Contact phone" value={contactPhone} onChangeText={setContactPhone} />

      <View style={styles.switchRow}>
        <Text>Visible to customer</Text>
        <Switch value={customerVisible} onValueChange={setCustomerVisible} disabled={isLoading} />
      </View>

      <Button
        title={isLoading ? 'Saving...' : 'Log communication'}
        onPress={() =>
          onSave(details.request.id, {
            direction,
            channel,
            subject: subject.trim() || undefined,
            message: message.trim(),
            outcome: outcome.trim() || undefined,
            contact_name: contactName.trim() || undefined,
            contact_email: contactEmail.trim() || undefined,
            contact_phone: contactPhone.trim() || undefined,
            customer_visible: customerVisible,
          })
        }
        disabled={isLoading || !message.trim()}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginTop: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#d8d8d8',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
  },
  templateBlock: {
    gap: 6,
  },
  sectionLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: '#4b5563',
    textTransform: 'uppercase',
  },
  rowWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  templateChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#93c5fd',
    backgroundColor: '#eff6ff',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  templateChipText: {
    color: '#1d4ed8',
    fontWeight: '600',
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#cccccc',
    backgroundColor: '#efefef',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  chipSelected: {
    borderColor: '#1d4d1a',
    backgroundColor: '#e2f2df',
  },
  chipText: {
    color: '#2f2f2f',
    textTransform: 'capitalize',
  },
  chipTextSelected: {
    color: '#1d4d1a',
    fontWeight: '700',
    textTransform: 'capitalize',
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
});
