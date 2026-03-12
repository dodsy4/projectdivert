import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { DispatchEligibilitySummary } from '../api/client';

type DispatchEligibilityPanelProps = {
  summary: DispatchEligibilitySummary | null | undefined;
  title?: string;
};

function formatLabel(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase());
}

function renderMissingReason(reason: string) {
  const [scope, code] = reason.split(':');
  if (!code) {
    return formatLabel(reason);
  }
  if (code === 'assignment') {
    return `${formatLabel(scope)} assignment missing`;
  }
  if (code === 'inactive') {
    return `${formatLabel(scope)} inactive`;
  }
  return `${formatLabel(scope)}: ${formatLabel(code)}`;
}

function SummaryBlock({
  label,
  summary,
}: {
  label: string;
  summary: DispatchEligibilitySummary['driver'] | DispatchEligibilitySummary['company'] | null;
}) {
  if (!summary) {
    return null;
  }

  return (
    <View style={styles.subsection}>
      <Text style={styles.subsectionTitle}>
        {label}: {summary.dispatch_eligible ? 'Ready' : 'Blocked'}
      </Text>
      {summary.required_document_types.map((documentType) => {
        const entry = summary.by_type?.[documentType];
        return (
          <View key={`${label}-${documentType}`} style={styles.row}>
            <Text style={styles.label}>{formatLabel(documentType)}</Text>
            <Text style={styles.value}>
              {entry?.verified
                ? 'Verified'
                : entry?.present
                  ? `Pending (${entry.latest_status || 'submitted'})`
                  : 'Missing'}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

export function DispatchEligibilityPanel({
  summary,
  title = 'Dispatch Eligibility',
}: DispatchEligibilityPanelProps) {
  if (!summary) {
    return null;
  }

  const companyName = summary.carrier_company?.name || 'Unassigned';

  return (
    <View style={styles.section}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.statusText}>
        Driver: {summary.driver.dispatch_eligible ? 'Ready' : 'Blocked'} | Company:{' '}
        {summary.company?.dispatch_eligible ? 'Ready' : 'Blocked'}
      </Text>
      <Text style={styles.companyText}>Carrier company: {companyName}</Text>
      {!summary.carrier_company_active && summary.carrier_company_assigned ? (
        <Text style={styles.warningText}>Assigned carrier company is inactive.</Text>
      ) : null}
      {summary.carrier_company_assigned ? null : (
        <Text style={styles.warningText}>No carrier company is assigned to this driver.</Text>
      )}
      {summary.driver.dispatch_eligible && summary.company?.dispatch_eligible ? null : (
        <View style={styles.subsection}>
          <Text style={styles.subsectionTitle}>Blockers</Text>
          {(summary.driver.dispatch_missing_document_types.length
            ? summary.driver.dispatch_missing_document_types.map((value) => `driver:${value}`)
            : []
          )
            .concat(
              !summary.carrier_company_assigned
                ? ['company:assignment']
                : !summary.carrier_company_active
                  ? ['company:inactive']
                  : (summary.company?.dispatch_missing_document_types || []).map(
                      (value) => `company:${value}`,
                    ),
            )
            .map((value) => (
              <Text key={value} style={styles.warningText}>
                • {renderMissingReason(value)}
              </Text>
            ))}
        </View>
      )}
      <SummaryBlock label="Driver documents" summary={summary.driver} />
      <SummaryBlock label="Company documents" summary={summary.company} />
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    borderTopWidth: 1,
    borderColor: '#e5e5e5',
    marginTop: 8,
    paddingTop: 8,
    gap: 6,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
  },
  statusText: {
    color: '#374151',
    fontWeight: '600',
  },
  companyText: {
    color: '#4b5563',
  },
  subsection: {
    gap: 3,
  },
  subsectionTitle: {
    color: '#111827',
    fontWeight: '700',
  },
  row: {
    gap: 2,
  },
  label: {
    color: '#111827',
    fontWeight: '600',
  },
  value: {
    color: '#4b5563',
  },
  warningText: {
    color: '#92400e',
    fontWeight: '600',
  },
});
