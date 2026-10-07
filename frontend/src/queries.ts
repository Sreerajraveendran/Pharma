// Shared, cached server data. Screens read lists through these hooks instead of fetching
// on every mount; after a change, `invalidate` refreshes exactly the affected lists.
import { QueryClient, useQuery } from '@tanstack/react-query';
import { getJson } from './api';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,          // tab switches within 30 s reuse cached data
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export const keys = {
  medicines: ['medicines'],
  batches: ['batches'],
  categories: ['categories'],
  patients: ['patients'],
  prescriptions: ['prescriptions'],
  patientPrescriptions: (patientId: string) => ['prescriptions', 'patient', patientId],
  dashboard: ['dashboard'],
  auditLogs: ['audit-logs'],
} as const;

export const useMedicines = () =>
  useQuery({ queryKey: keys.medicines, queryFn: () => getJson<any[]>('/api/medicines') });

export const useBatches = () =>
  useQuery({ queryKey: keys.batches, queryFn: () => getJson<any[]>('/api/batches') });

export const useCategories = () =>
  useQuery({ queryKey: keys.categories, queryFn: () => getJson<any[]>('/api/categories') });

export const usePatients = () =>
  useQuery({ queryKey: keys.patients, queryFn: () => getJson<any[]>('/api/patients') });

export const usePatientPrescriptions = (patientId: string | null | undefined) =>
  useQuery({
    queryKey: keys.patientPrescriptions(patientId || ''),
    queryFn: () => getJson<any[]>(`/api/patients/${patientId}/prescriptions`),
    enabled: !!patientId,
  });

export const useDashboard = () =>
  useQuery({
    queryKey: keys.dashboard,
    queryFn: () => getJson<any>(`/api/dashboard/metrics?tz_offset=${-new Date().getTimezoneOffset()}`),
  });

export const useAuditLogs = (limit: number) =>
  useQuery({ queryKey: [...keys.auditLogs, limit], queryFn: () => getJson<any[]>(`/api/pos/audit-logs?limit=${limit}`) });

// What each kind of change makes stale
export const invalidate = {
  stock: () => Promise.all([keys.medicines, keys.batches, keys.dashboard, keys.auditLogs]
    .map(queryKey => queryClient.invalidateQueries({ queryKey }))),
  catalog: () => Promise.all([keys.medicines, keys.batches, keys.categories, keys.dashboard]
    .map(queryKey => queryClient.invalidateQueries({ queryKey }))),
  patients: () => queryClient.invalidateQueries({ queryKey: keys.patients }),
  prescriptions: () => Promise.all([keys.prescriptions, keys.dashboard]
    .map(queryKey => queryClient.invalidateQueries({ queryKey }))),
  sale: () => Promise.all([keys.medicines, keys.batches, keys.prescriptions, keys.dashboard, keys.auditLogs]
    .map(queryKey => queryClient.invalidateQueries({ queryKey }))),
};
