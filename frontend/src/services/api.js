import axios from 'axios';

// Use environment variable or default to current host's backend
const API_BASE_URL = import.meta.env.VITE_API_URL ||
  (window.location.hostname === 'localhost'
    ? 'http://localhost:8000/api'
    : `http://${window.location.hostname}:8000/api`);

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Project API
export const projectAPI = {
  getAll: () => api.get('/projects/'),
  getById: (id) => api.get(`/projects/${id}/`),
  create: (data) => api.post('/projects/', data),
  update: (id, data) => api.put(`/projects/${id}/`, data),
  delete: (id) => api.delete(`/projects/${id}/`),
  getState: (id) => api.get(`/projects/${id}/state`),
  generate: (id, force = false) => api.post(`/projects/${id}/generate?force=${force}`),
  sync: (id) => api.post(`/projects/${id}/sync`),
  download: (id) => api.get(`/projects/${id}/download`, { responseType: 'blob' }),
};

// Data Models API
export const modelAPI = {
  getAll: (projectId) => api.get(`/projects/${projectId}/models/`),
  getById: (projectId, modelId) => api.get(`/projects/${projectId}/models/${modelId}/`),
  create: (projectId, data) => api.post(`/projects/${projectId}/models/`, data),
  update: (projectId, modelId, data) => api.put(`/projects/${projectId}/models/${modelId}/`, data),
  delete: (projectId, modelId) => api.delete(`/projects/${projectId}/models/${modelId}/`),
};

// Relationships API
export const relationAPI = {
  getAll: (projectId, modelId) => api.get(`/projects/${projectId}/models/${modelId}/relations/`),
  getById: (projectId, modelId, relationId) => api.get(`/projects/${projectId}/models/${modelId}/relations/${relationId}/`),
  create: (projectId, modelId, data) => api.post(`/projects/${projectId}/models/${modelId}/relations/`, data),
  update: (projectId, modelId, relationId, data) => api.put(`/projects/${projectId}/models/${modelId}/relations/${relationId}/`, data),
  delete: (projectId, modelId, relationId) => api.delete(`/projects/${projectId}/models/${modelId}/relations/${relationId}/`),
};

// Services API
export const serviceAPI = {
  getAll: (projectId) => api.get(`/projects/${projectId}/services/`),
  getById: (projectId, serviceId) => api.get(`/projects/${projectId}/services/${serviceId}/`),
  create: (projectId, data) => api.post(`/projects/${projectId}/services/`, data),
  update: (projectId, serviceId, data) => api.put(`/projects/${projectId}/services/${serviceId}/`, data),
  delete: (projectId, serviceId) => api.delete(`/projects/${projectId}/services/${serviceId}/`),
};

// Middlewares API
export const middlewareAPI = {
  getAll: (projectId) => api.get(`/projects/${projectId}/middlewares/`),
  create: (projectId, data) => api.post(`/projects/${projectId}/middlewares/`, data),
};

// Dependencies API
export const dependencyAPI = {
  getAll: (projectId) => api.get(`/projects/${projectId}/dependencies/`),
  getById: (projectId, dependencyId) => api.get(`/projects/${projectId}/dependencies/${dependencyId}/`),
  create: (projectId, data) => api.post(`/projects/${projectId}/dependencies/`, data),
  update: (projectId, dependencyId, data) => api.put(`/projects/${projectId}/dependencies/${dependencyId}/`, data),
  delete: (projectId, dependencyId) => api.delete(`/projects/${projectId}/dependencies/${dependencyId}/`),
};

// Service Schemas API
export const schemaAPI = {
  getAll: (projectId, serviceId) => api.get(`/projects/${projectId}/services/${serviceId}/schemas/`),
  getById: (projectId, serviceId, schemaId) => api.get(`/projects/${projectId}/services/${serviceId}/schemas/${schemaId}/`),
  create: (projectId, serviceId, data) => api.post(`/projects/${projectId}/services/${serviceId}/schemas/`, data),
  update: (projectId, serviceId, schemaId, data) => api.put(`/projects/${projectId}/services/${serviceId}/schemas/${schemaId}/`, data),
  delete: (projectId, serviceId, schemaId) => api.delete(`/projects/${projectId}/services/${serviceId}/schemas/${schemaId}/`),
};

// Service Functions API
export const functionAPI = {
  getAll: (projectId, serviceId) => api.get(`/projects/${projectId}/services/${serviceId}/functions/`),
  getById: (projectId, serviceId, functionId) => api.get(`/projects/${projectId}/services/${serviceId}/functions/${functionId}/`),
  create: (projectId, serviceId, data) => api.post(`/projects/${projectId}/services/${serviceId}/functions/`, data),
  update: (projectId, serviceId, functionId, data) => api.put(`/projects/${projectId}/services/${serviceId}/functions/${functionId}/`, data),
  delete: (projectId, serviceId, functionId) => api.delete(`/projects/${projectId}/services/${serviceId}/functions/${functionId}/`),
};

// Service Endpoints API
export const endpointAPI = {
  getAll: (projectId, serviceId) => api.get(`/projects/${projectId}/services/${serviceId}/endpoints/`),
  getById: (projectId, serviceId, endpointId) => api.get(`/projects/${projectId}/services/${serviceId}/endpoints/${endpointId}/`),
  create: (projectId, serviceId, data) => api.post(`/projects/${projectId}/services/${serviceId}/endpoints/`, data),
  update: (projectId, serviceId, endpointId, data) => api.put(`/projects/${projectId}/services/${serviceId}/endpoints/${endpointId}/`, data),
  delete: (projectId, serviceId, endpointId) => api.delete(`/projects/${projectId}/services/${serviceId}/endpoints/${endpointId}/`),
};

// Configuration API
export const configAPI = {
  database: {
    get: (projectId) => api.get(`/projects/${projectId}/config/database/`),
    create: (projectId, data) => api.post(`/projects/${projectId}/config/database/`, data),
    update: (projectId, data) => api.put(`/projects/${projectId}/config/database/`, data),
  },
  framework: {
    get: (projectId) => api.get(`/projects/${projectId}/config/framework/`),
    create: (projectId, data) => api.post(`/projects/${projectId}/config/framework/`, data),
    update: (projectId, data) => api.put(`/projects/${projectId}/config/framework/`, data),
  },
  security: {
    get: (projectId) => api.get(`/projects/${projectId}/config/security/`),
    create: (projectId, data) => api.post(`/projects/${projectId}/config/security/`, data),
    update: (projectId, data) => api.put(`/projects/${projectId}/config/security/`, data),
  },
};

export default api;
