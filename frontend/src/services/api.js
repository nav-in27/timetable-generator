/**
 * API Service for Timetable Generator
 * Handles all HTTP requests to the backend
 */
import axios from 'axios';

// Use environment variable for API URL (set in Vercel/Render dashboard)
// Falls back to localhost for development or relative path for same-origin production
let rawApiUrl = import.meta.env.VITE_API_URL || '';
const hasExplicitApiUrl = Boolean(rawApiUrl);

// Smart fix for common deployment misconfigurations
if (rawApiUrl) {
  // Ensure it has a protocol
  if (!rawApiUrl.startsWith('http')) {
    rawApiUrl = `https://${rawApiUrl}`;
  }
  // Ensure it has the /api suffix if missing
  if (!rawApiUrl.endsWith('/api')) {
    rawApiUrl = rawApiUrl.endsWith('/') ? `${rawApiUrl}api` : `${rawApiUrl}/api`;
  }
}

// Fallback logic:
// 1. If VITE_API_URL is provided, use it.
// 2. In development, use localhost:8000.
// 3. In production, use relative /api (assumes same-origin hosting).
const DEFAULT_API_BASE_URL = rawApiUrl || (import.meta.env.DEV ? 'http://127.0.0.1:8000/api' : '/api');

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

const getPortFromBaseUrl = (url) => {
  try {
    const parsed = new URL(url);
    return parsed.port ? parseInt(parsed.port, 10) : null;
  } catch {
    return null;
  }
};

const detectLocalApiBaseUrl = async (preferredPort = null) => {
  const hostname = window.location.hostname || '127.0.0.1';
  const safeHost = isLocalHostname(hostname) ? hostname : '127.0.0.1';
  const candidatePorts = [8000, 8001, 8002, 8003, 8004, 8005];
  const ports = preferredPort && candidatePorts.includes(preferredPort)
    ? [preferredPort, ...candidatePorts.filter((port) => port !== preferredPort)]
    : candidatePorts;

  for (const port of ports) {
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
      !hasExplicitApiUrl &&
      !hasAutoDetected &&
      !error.response &&
      isLocalBaseUrl(api.defaults.baseURL);

    if (!shouldTryDetect) {
      return Promise.reject(error);
    }

    if (!autoDetectInFlight) {
      autoDetectInFlight = detectLocalApiBaseUrl(
        getPortFromBaseUrl(api.defaults.baseURL)
      ).finally(() => {
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
  getStats: (deptId = null) => {
    const params = deptId ? `?dept_id=${deptId}` : '';
    return api.get(`/dashboard/stats${params}`);
  },
  getRecentSubstitutions: () => api.get('/dashboard/recent-substitutions'),
};

// Teacher Load Dashboard
export const teacherLoadApi = {
  getDashboard: (params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.deptId) searchParams.append('dept_id', params.deptId);
    if (params.year) searchParams.append('year', params.year);
    const suffix = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return api.get(`/dashboard/teacher-load${suffix}`);
  },
};

// ============================================================================
// Departments
// ============================================================================
export const departmentsApi = {
  getAll: () => api.get('/departments/'),
  getById: (id) => api.get(`/departments/${id}`),
  create: (data) => api.post('/departments/', data),
  update: (id, data) => api.put(`/departments/${id}`, data),
  delete: (id) => api.delete(`/departments/${id}`),
};

// ============================================================================
// Rule Toggles (Department-Specific)
// ============================================================================
export const ruleTogglesApi = {
  getAll: () => api.get('/rule-toggles/'),
  getByDept: (deptId) => api.get(`/rule-toggles/${deptId}`),
  update: (deptId, data) => api.put(`/rule-toggles/${deptId}`, data),
};

// ============================================================================
// Reports (Accreditation)
// ============================================================================
const buildDeptQuery = (deptId) => (deptId ? `?dept_id=${deptId}` : '');

export const reportsApi = {
  getTeacherWorkload: (deptId = null) =>
    api.get(`/reports/teacher-workload${buildDeptQuery(deptId)}`),
  getRoomUtilization: (deptId = null) =>
    api.get(`/reports/room-utilization${buildDeptQuery(deptId)}`),
  getSubjectCoverage: (deptId = null) =>
    api.get(`/reports/subject-coverage${buildDeptQuery(deptId)}`),
  getTeacherWorkloadPdfUrl: (deptId = null) =>
    `${api.defaults.baseURL}/reports/teacher-workload/pdf${buildDeptQuery(deptId)}`,
  getRoomUtilizationPdfUrl: (deptId = null) =>
    `${api.defaults.baseURL}/reports/room-utilization/pdf${buildDeptQuery(deptId)}`,
  getSubjectCoveragePdfUrl: (deptId = null) =>
    `${api.defaults.baseURL}/reports/subject-coverage/pdf${buildDeptQuery(deptId)}`,
  getMasterLabTimetable: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.deptId) params.append('dept_id', filters.deptId);
    if (filters.semesterType) params.append('semester_type', filters.semesterType);
    return api.get(`/reports/master-lab?${params.toString()}`);
  }
};

// ============================================================================
// Teachers
// ============================================================================
export const teachersApi = {
  getAll: (activeOnly = true, deptId = null) => {
    let url = `/teachers/?active_only=${activeOnly}`;
    if (deptId) url += `&dept_id=${deptId}`;
    return api.get(url);
  },
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
  getAll: (params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.deptId) searchParams.append('dept_id', params.deptId);
    if (params.year) searchParams.append('year', params.year);
    if (params.semester) searchParams.append('semester', params.semester);
    if (params.isElective !== undefined) searchParams.append('is_elective', params.isElective);
    return api.get(`/subjects/?${searchParams.toString()}`);
  },
  getById: (id) => api.get(`/subjects/${id}`),
  create: (data) => api.post('/subjects/', data),
  update: (id, data) => api.put(`/subjects/${id}`, data),
  delete: (id) => api.delete(`/subjects/${id}`),
};

// ============================================================================
// Semesters/Classes
// ============================================================================
export const semestersApi = {
  getAll: (params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.deptId) searchParams.append('dept_id', params.deptId);
    return api.get(`/semesters/?${searchParams.toString()}`);
  },
  getById: (id) => api.get(`/semesters/${id}`),
  create: (data) => api.post('/semesters/', data),
  update: (id, data) => api.put(`/semesters/${id}`, data),
  delete: (id) => api.delete(`/semesters/${id}`),
  // Batches
  getBatches: (id) => api.get(`/semesters/${id}/batches`),
  createBatch: (id, data) => api.post(`/semesters/${id}/batches`, data),
  deleteBatch: (id, batchId) => api.delete(`/semesters/${id}/batches/${batchId}`),
};

// ============================================================================
// Rooms
// ============================================================================
export const roomsApi = {
  getAll: (params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.deptId) searchParams.append('dept_id', params.deptId);
    const suffix = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return api.get(`/rooms/${suffix}`);
  },
  getById: (id) => api.get(`/rooms/${id}`),
  create: (data) => api.post('/rooms/', data),
  update: (id, data) => api.put(`/rooms/${id}`, data),
  delete: (id) => api.delete(`/rooms/${id}`),
};

// ============================================================================
// Room Availability (Analytics / Dashboard)
// ============================================================================
export const roomAvailabilityApi = {
  getSchedule: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.deptId) sp.append('dept_id', params.deptId);
    if (params.roomType) sp.append('room_type', params.roomType);
    if (params.roomId) sp.append('room_id', params.roomId);
    return api.get(`/room-availability/schedule?${sp.toString()}`);
  },
  getFreeRooms: (day, slot, params = {}) => {
    const sp = new URLSearchParams();
    sp.append('day', day);
    sp.append('slot', slot);
    if (params.deptId) sp.append('dept_id', params.deptId);
    if (params.roomType) sp.append('room_type', params.roomType);
    if (params.minCapacity) sp.append('min_capacity', params.minCapacity);
    return api.get(`/room-availability/free-rooms?${sp.toString()}`);
  },
  getSummary: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.deptId) sp.append('dept_id', params.deptId);
    return api.get(`/room-availability/summary?${sp.toString()}`);
  },
  suggest: (day, slot, params = {}) => {
    const sp = new URLSearchParams();
    sp.append('day', day);
    sp.append('slot', slot);
    if (params.deptId) sp.append('dept_id', params.deptId);
    if (params.roomType) sp.append('room_type', params.roomType);
    if (params.minCapacity) sp.append('min_capacity', params.minCapacity);
    if (params.consecutive) sp.append('consecutive', params.consecutive);
    return api.get(`/room-availability/suggest?${sp.toString()}`);
  },
};

// ============================================================================
// Parallel Lab Baskets
// ============================================================================
export const parallelLabBasketsApi = {
  getAll: (deptId = null) => {
    const params = deptId ? `?dept_id=${deptId}` : '';
    return api.get(`/parallel-lab-baskets/${params}`);
  },
  create: (data) => api.post('/parallel-lab-baskets/', data),
  update: (id, data) => api.put(`/parallel-lab-baskets/${id}`, data),
  delete: (id) => api.delete(`/parallel-lab-baskets/${id}`),
};

// ============================================================================
// Timetable
// ============================================================================
export const timetableApi = {
  generate: (data = {}) => api.post('/timetable/generate', data),
  generateAsync: (data = {}) => api.post('/timetable/generate/async', data),
  getGenerationStatus: (taskId) => api.get(`/timetable/generate/status/${taskId}`),
  getAllocations: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.semesterId) params.append('semester_id', filters.semesterId);
    if (filters.teacherId) params.append('teacher_id', filters.teacherId);
    if (filters.day !== undefined) params.append('day', filters.day);
    if (filters.deptId) params.append('dept_id', filters.deptId);
    return api.get(`/timetable/allocations?${params}`);
  },
  getBySemester: (semesterId, viewDate = null) => {
    const params = viewDate ? `?view_date=${viewDate}` : '';
    return api.get(`/timetable/view/semester/${semesterId}${params}`);
  },
  getByTeacher: (teacherId, viewDate = null, deptId = null) => {
    const parts = [];
    if (viewDate) parts.push(`view_date=${viewDate}`);
    if (deptId) parts.push(`dept_id=${deptId}`);
    const params = parts.length > 0 ? `?${parts.join('&')}` : '';
    return api.get(`/timetable/view/teacher/${teacherId}${params}`);
  },
  clear: (semesterId = null, deptId = null) => {
    const parts = [];
    if (semesterId) parts.push(`semester_id=${semesterId}`);
    if (deptId) parts.push(`dept_id=${deptId}`);
    const params = parts.length > 0 ? `?${parts.join('&')}` : '';
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

// ============================================================================
// Structured Composite Baskets
// ============================================================================
export const structuredCompositeBasketsApi = {
  getAll: () => api.get('/structured-composite-baskets/'),
  getById: (id) => api.get(`/structured-composite-baskets/${id}`),
  create: (data) => api.post('/structured-composite-baskets/', data),
  update: (id, data) => api.put(`/structured-composite-baskets/${id}`, data),
  delete: (id) => api.delete(`/structured-composite-baskets/${id}`),
};



// ============================================================================
// Allocation Engine (Module 3-6)
// ============================================================================
export const allocationApi = {
  runAllocation: (data) => api.post('/allocation/run', data),
  getMode: () => api.get('/allocation/mode'),
  setMode: (mode) => api.put('/allocation/mode', { mode }),
  getAssignments: (params = {}) => api.get('/allocation/assignments', { params }),
  updateAssignment: (id, data) => api.put(`/allocation/assignments/${id}`, data),
  swapAssignments: (idA, idB) => api.post('/allocation/assignments/swap', {
    assignment_id_a: idA, assignment_id_b: idB,
  }),
  deleteAssignment: (id) => api.delete(`/allocation/assignments/${id}`),
  lockAssignment: (id) => api.put(`/allocation/assignments/${id}/lock`),
  unlockAssignment: (id) => api.put(`/allocation/assignments/${id}/unlock`),
  getWorkload: (params = {}) => api.get('/allocation/workload', { params }),
};

// ============================================================================
// Feasibility Analyzer (Module 9)
// ============================================================================
export const feasibilityApi = {
  analyze: (params = {}) => api.get('/feasibility/analyze', { params }),
};

export default api;
