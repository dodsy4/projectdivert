import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ScreenTab } from '../features/wasteMobile/types';

type ScreenTabsProps = {
  items: ScreenTab[];
  activeId: string;
  onPress: (id: string) => void;
};

export function ScreenTabs({ items, activeId, onPress }: ScreenTabsProps) {
  return (
    <View style={styles.tabBar}>
      {items.map((tab) => {
        const selected = tab.id === activeId;
        return (
          <Pressable
            key={tab.id}
            onPress={() => onPress(tab.id)}
            style={[styles.tabButton, selected ? styles.tabButtonSelected : undefined]}
          >
            <Text
              style={[
                styles.tabButtonText,
                selected ? styles.tabButtonTextSelected : undefined,
              ]}
            >
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tabButton: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#cccccc',
    backgroundColor: '#efefef',
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  tabButtonSelected: {
    borderColor: '#1e4f9f',
    backgroundColor: '#dfeaff',
  },
  tabButtonText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#2f2f2f',
  },
  tabButtonTextSelected: {
    color: '#123b74',
  },
});
