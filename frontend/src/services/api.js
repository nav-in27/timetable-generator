/**
 * API Service for Timetable Generator
 * Handles all HTTP requests to the backend
 */
import axios from 'axios';

// Use environment variable for API URL (set in Vercel dashboard)
// Falls back to localhost for development
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

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

export default api;
