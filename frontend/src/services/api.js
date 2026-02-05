/**
 * API Service for Timetable Generator
 * Handles all HTTP requests to the backend
 */
import axios from 'axios';

// Use environment variable for API URL (set in Vercel dashboard)
// Falls back to localhost for development
const DEFAULT_API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api';

const api = axios.create({
  baseURL: DEFAULT_API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const isLocalHostname = (hostname) =>
  hostname === 'localhost' || hostname === '127.0.0.1';

const isLocalBaseUrl = (url) => {
  try {
    const parsed = new URL(url);
    return isLocalHostname(parsed.hostname);
  } catch {
    return false;
  }
};

const withTimeout = async (promise, ms) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), ms);
  try {
    const result = await promise(controller.signal);
    return result;
  } finally {
    clearTimeout(timeout);
  }
};

const detectLocalApiBaseUrl = async () => {
  const hostname = window.location.hostname || '127.0.0.1';
  const safeHost = isLocalHostname(hostname) ? hostname : '127.0.0.1';
  const candidatePorts = [8000, 8001, 8002, 8003, 8004, 8005];

  for (const port of candidatePorts) {
    const healthUrl = `http://${safeHost}:${port}/health`;
    try {
      const response = await withTimeout(
        (signal) => fetch(healthUrl, { signal }),
        600
      );
      if (response.ok) {
        return `http://${safeHost}:${port}/api`;
      }
    } catch {
      // Ignore and try next port
    }
  }
  return null;
};

let autoDetectInFlight = null;
let hasAutoDetected = false;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const shouldTryDetect =
      import.meta.env.DEV &&
      !hasAutoDetected &&
      !error.response &&
      isLocalBaseUrl(api.defaults.baseURL);

    if (!shouldTryDetect) {
      return Promise.reject(error);
    }

    if (!autoDetectInFlight) {
      autoDetectInFlight = detectLocalApiBaseUrl().finally(() => {
        autoDetectInFlight = null;
      });
    }

    const detectedBase = await autoDetectInFlight;
    hasAutoDetected = true;

    if (!detectedBase || detectedBase === api.defaults.baseURL) {
      return Promise.reject(error);
    }

    api.defaults.baseURL = detectedBase;
    const retryConfig = { ...error.config, baseURL: detectedBase };
    return api.request(retryConfig);
  }
);

// ============================================================================
// Dashboard
// ============================================================================
export const dashboardApi = {
  getStats: () => api.get('/dashboard/stats'),
  getRecentSubstitutions: () => api.get('/dashboard/recent-substitutions'),
};

// ============================================================================
// Teachers
// ============================================================================
export const teachersApi = {
  getAll: (activeOnly = true) => api.get(`/teachers/?active_only=${activeOnly}`),
  getById: (id) => api.get(`/teachers/${id}`),
  create: (data) => api.post('/teachers/', data),
  update: (id, data) => api.put(`/teachers/${id}`, data),
  delete: (id) => api.delete(`/teachers/${id}`),
  addSubject: (teacherId, subjectId, effectivenessScore = 0.8) =>
    api.post(`/teachers/${teacherId}/subjects/${subjectId}?effectiveness_score=${effectivenessScore}`),
  removeSubject: (teacherId, subjectId) =>
    api.delete(`/teachers/${teacherId}/subjects/${subjectId}`),
  addAssignment: (teacherId, data) =>
    api.post(`/teachers/${teacherId}/assignments`, data),
  removeAssignment: (assignmentId) =>
    api.delete(`/teachers/assignments/${assignmentId}`),
};

// ============================================================================
// Subjects
// ============================================================================
export const subjectsApi = {
  getAll: () => api.get('/subjects/'),
  getById: (id) => api.get(`/subjects/${id}`),
  create: (data) => api.post('/subjects/', data),
  update: (id, data) => api.put(`/subjects/${id}`, data),
  delete: (id) => api.delete(`/subjects/${id}`),
};

// ============================================================================
// Semesters/Classes
// ============================================================================
export const semestersApi = {
  getAll: () => api.get('/semesters/'),
  getById: (id) => api.get(`/semesters/${id}`),
  create: (data) => api.post('/semesters/', data),
  update: (id, data) => api.put(`/semesters/${id}`, data),
  delete: (id) => api.delete(`/semesters/${id}`),
};

// ============================================================================
// Rooms
// ============================================================================
export const roomsApi = {
  getAll: () => api.get('/rooms/'),
  getById: (id) => api.get(`/rooms/${id}`),
  create: (data) => api.post('/rooms/', data),
  update: (id, data) => api.put(`/rooms/${id}`, data),
  delete: (id) => api.delete(`/rooms/${id}`),
};

// ============================================================================
// Timetable
// ============================================================================
export const timetableApi = {
  generate: (data = {}) => api.post('/timetable/generate', data),
  getAllocations: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.semesterId) params.append('semester_id', filters.semesterId);
    if (filters.teacherId) params.append('teacher_id', filters.teacherId);
    if (filters.day !== undefined) params.append('day', filters.day);
    return api.get(`/timetable/allocations?${params}`);
  },
  getBySemester: (semesterId, viewDate = null) => {
    const params = viewDate ? `?view_date=${viewDate}` : '';
    return api.get(`/timetable/view/semester/${semesterId}${params}`);
  },
  getByTeacher: (teacherId, viewDate = null) => {
    const params = viewDate ? `?view_date=${viewDate}` : '';
    return api.get(`/timetable/view/teacher/${teacherId}${params}`);
  },
  clear: (semesterId = null) => {
    const params = semesterId ? `?semester_id=${semesterId}` : '';
    return api.delete(`/timetable/clear${params}`);
  },
  // PDF Export (READ-ONLY operations)
  getExportStatus: () => api.get('/timetable/export/status'),
  getPreviewUrl: () => `${api.defaults.baseURL}/timetable/export/pdf/preview`,
  getDownloadUrl: () => `${api.defaults.baseURL}/timetable/export/pdf`,
};

// ============================================================================
// Substitution
// ============================================================================
export const substitutionApi = {
  markAbsent: (data) => api.post('/substitution/mark-absent', data),
  getAbsences: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.teacherId) params.append('teacher_id', filters.teacherId);
    if (filters.fromDate) params.append('from_date', filters.fromDate);
    if (filters.toDate) params.append('to_date', filters.toDate);
    return api.get(`/substitution/absences?${params}`);
  },
  getAffectedAllocations: (teacherId, absenceDate) =>
    api.get(`/substitution/affected-allocations/${teacherId}/${absenceDate}`),
  getCandidates: (allocationId, substitutionDate) =>
    api.get(`/substitution/candidates/${allocationId}/${substitutionDate}`),
  assign: (data, substituteTeacherId = null) => {
    const params = substituteTeacherId ? `?substitute_teacher_id=${substituteTeacherId}` : '';
    return api.post(`/substitution/assign${params}`, data);
  },
  autoSubstitute: (teacherId, absenceDate, reason = null) => {
    const params = reason ? `?reason=${encodeURIComponent(reason)}` : '';
    return api.post(`/substitution/auto-substitute/${teacherId}/${absenceDate}${params}`);
  },
  getActive: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.fromDate) params.append('from_date', filters.fromDate);
    if (filters.toDate) params.append('to_date', filters.toDate);
    return api.get(`/substitution/active?${params}`);
  },
  cancel: (id) => api.delete(`/substitution/${id}`),
};

// ============================================================================
// Fixed Slots (Manual Slot Locking)
// ============================================================================
export const fixedSlotsApi = {
  // Get all fixed slots, optionally filtered by semester
  getAll: (semesterId = null) => {
    const params = semesterId ? `?semester_id=${semesterId}` : '';
    return api.get(`/fixed-slots/${params}`);
  },
  // Get fixed slots grouped by semester
  getBySemester: () => api.get('/fixed-slots/by-semester'),
  // Get a specific fixed slot
  getById: (id) => api.get(`/fixed-slots/${id}`),
  // Create a new fixed slot (lock a slot)
  create: (data) => api.post('/fixed-slots/', data),
  // Delete a fixed slot (unlock)
  delete: (id) => api.delete(`/fixed-slots/${id}`),
  // Clear all fixed slots for a semester
  clearSemester: (semesterId) => api.delete(`/fixed-slots/clear/semester/${semesterId}`),
  // Clear all fixed slots (admin only)
  clearAll: () => api.delete('/fixed-slots/clear/all'),
  // Validate if a slot can be locked (without actually locking it)
  validate: (data) => api.post('/fixed-slots/validate', data),
};

export default api;
