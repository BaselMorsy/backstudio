import { useState, useEffect } from 'react';
import { X, Save, Code, Layers, Route, Plus } from 'lucide-react';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import { serviceAPI, schemaAPI, functionAPI, endpointAPI, dependencyAPI } from '../../services/api';
import AddSchemaModal from './AddSchemaModal';
import AddFunctionModal from './AddFunctionModal';
import AddEndpointModal from './AddEndpointModal';

function ServiceDetailModal({ service, projectId, onClose, onUpdate }) {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState('basic');
  const [editMode, setEditMode] = useState(false);
  const [formData, setFormData] = useState({
    name: service.name,
    description: service.description || '',
    is_singleton: service.is_singleton ?? true,
  });
  const [saving, setSaving] = useState(false);

  // Data states
  const [schemas, setSchemas] = useState([]);
  const [functions, setFunctions] = useState([]);
  const [endpoints, setEndpoints] = useState([]);
  const [dependencies, setDependencies] = useState([]);
  const [loading, setLoading] = useState(false);

  // Modal states
  const [showAddSchema, setShowAddSchema] = useState(false);
  const [showAddFunction, setShowAddFunction] = useState(false);
  const [showAddEndpoint, setShowAddEndpoint] = useState(false);
  const [editingSchema, setEditingSchema] = useState(null);
  const [editingFunction, setEditingFunction] = useState(null);
  const [editingEndpoint, setEditingEndpoint] = useState(null);

  const tabs = [
    { id: 'basic', label: 'Basic Info', icon: Code },
    { id: 'schemas', label: 'Schemas', icon: Layers },
    { id: 'functions', label: 'Functions', icon: Code },
    { id: 'endpoints', label: 'Endpoints', icon: Route },
  ];

  // Fetch dependencies on mount
  useEffect(() => {
    const fetchDependencies = async () => {
      try {
        const response = await dependencyAPI.getAll(projectId);
        setDependencies(response.data);
      } catch (error) {
        console.error('Failed to fetch dependencies:', error);
      }
    };
    fetchDependencies();
  }, [projectId]);

  // Fetch data when tab changes
  useEffect(() => {
    fetchTabData();
  }, [activeTab, projectId, service.id]);

  const fetchTabData = async () => {
    if (activeTab === 'schemas') {
      setLoading(true);
      try {
        const response = await schemaAPI.getAll(projectId, service.id);
        setSchemas(response.data);
      } catch (error) {
        console.error('Failed to fetch schemas:', error);
      } finally {
        setLoading(false);
      }
    } else if (activeTab === 'functions') {
      setLoading(true);
      try {
        const response = await functionAPI.getAll(projectId, service.id);
        setFunctions(response.data);
      } catch (error) {
        console.error('Failed to fetch functions:', error);
      } finally {
        setLoading(false);
      }
    } else if (activeTab === 'endpoints') {
      setLoading(true);
      try {
        const response = await endpointAPI.getAll(projectId, service.id);
        setEndpoints(response.data);
      } catch (error) {
        console.error('Failed to fetch endpoints:', error);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleSchemaAdded = () => {
    setShowAddSchema(false);
    fetchTabData();
  };

  const handleFunctionAdded = () => {
    setShowAddFunction(false);
    fetchTabData();
  };

  const handleEndpointAdded = () => {
    setShowAddEndpoint(false);
    fetchTabData();
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      toast.showWarning('Service name is required');
      return;
    }

    try {
      setSaving(true);
      const response = await serviceAPI.update(projectId, service.id, formData);
      onUpdate(response.data);
      setEditMode(false);
      toast.showSuccess('Service updated successfully');
    } catch (error) {
      console.error('Failed to update service:', error);
      toast.showError(error.response?.data?.detail || 'Failed to update service');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setFormData({
      name: service.name,
      description: service.description || '',
      is_singleton: service.is_singleton ?? true,
    });
    setEditMode(false);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-primary-100 p-2 rounded-lg">
              <Code className="w-6 h-6 text-primary-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-800">
                {service.name}
              </h2>
              <p className="text-sm text-gray-500">Service Details</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b">
          <div className="flex gap-1 px-6">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-4 py-3 font-medium transition-colors border-b-2 flex items-center gap-2 ${
                    activeTab === tab.id
                      ? 'border-primary-600 text-primary-600'
                      : 'border-transparent text-gray-600 hover:text-gray-800'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'basic' && (
            <div className="space-y-4">
              {editMode ? (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Service Name *
                    </label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                      placeholder="e.g., UserService"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Description
                    </label>
                    <textarea
                      value={formData.description}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                      rows="3"
                      placeholder="Service description..."
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="is_singleton"
                      checked={formData.is_singleton}
                      onChange={(e) => setFormData({ ...formData, is_singleton: e.target.checked })}
                      className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                    />
                    <label htmlFor="is_singleton" className="text-sm text-gray-700">
                      Singleton (single instance across application)
                    </label>
                  </div>

                  <div className="flex gap-3 pt-4">
                    <Button onClick={handleSave} disabled={saving}>
                      <Save className="w-4 h-4 mr-2" />
                      {saving ? 'Saving...' : 'Save Changes'}
                    </Button>
                    <Button variant="outline" onClick={handleCancel} disabled={saving}>
                      Cancel
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Service Name
                    </label>
                    <p className="text-gray-800">{service.name}</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Description
                    </label>
                    <p className="text-gray-800">
                      {service.description || <span className="text-gray-400">No description</span>}
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Type
                    </label>
                    <p className="text-gray-800">
                      {service.is_singleton ? 'Singleton' : 'Transient'}
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Service ID
                    </label>
                    <code className="text-sm text-gray-600 bg-gray-100 px-2 py-1 rounded">
                      {service.id}
                    </code>
                  </div>

                  <Button onClick={() => setEditMode(true)} className="mt-4">
                    Edit Service
                  </Button>
                </>
              )}
            </div>
          )}

          {activeTab === 'schemas' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-800">
                  Schemas (DTOs)
                </h3>
                <Button size="sm" onClick={() => setShowAddSchema(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Add Schema
                </Button>
              </div>

              {loading ? (
                <div className="text-center py-12 text-gray-500">Loading schemas...</div>
              ) : schemas.length === 0 ? (
                <div className="text-center py-12">
                  <Layers className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500 mb-4">No schemas defined yet</p>
                  <p className="text-sm text-gray-400">
                    Click "Add Schema" to create your first schema
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {schemas.map((schema) => (
                    <div
                      key={schema.id}
                      className="border border-gray-200 rounded-lg p-4 hover:border-primary-300 transition-colors cursor-pointer hover:shadow-md"
                      onClick={() => setEditingSchema(schema)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h4 className="font-medium text-gray-800">{schema.name}</h4>
                          {schema.description && (
                            <p className="text-sm text-gray-600 mt-1">{schema.description}</p>
                          )}
                          <div className="mt-2 flex items-center gap-2 text-sm text-gray-500">
                            <span>{schema.fields?.length || 0} field(s)</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'functions' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-800">
                  Service Functions
                </h3>
                <Button size="sm" onClick={() => setShowAddFunction(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Add Function
                </Button>
              </div>

              {loading ? (
                <div className="text-center py-12 text-gray-500">Loading functions...</div>
              ) : functions.length === 0 ? (
                <div className="text-center py-12">
                  <Code className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500 mb-4">No functions defined yet</p>
                  <p className="text-sm text-gray-400">
                    Click "Add Function" to create your first function
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {functions.map((func) => (
                    <div
                      key={func.id}
                      className="border border-gray-200 rounded-lg p-4 hover:border-primary-300 transition-colors cursor-pointer hover:shadow-md"
                      onClick={() => setEditingFunction(func)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h4 className="font-medium text-gray-800">{func.name}</h4>
                            {func.is_async && (
                              <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                                async
                              </span>
                            )}
                          </div>
                          {func.description && (
                            <p className="text-sm text-gray-600 mt-1">{func.description}</p>
                          )}
                          <div className="mt-2 flex items-center gap-3 text-sm text-gray-500">
                            <span>{func.parameters?.length || 0} parameter(s)</span>
                            {func.return_type && (
                              <span>→ {func.return_type}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'endpoints' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-800">
                  API Endpoints
                </h3>
                <Button size="sm" onClick={() => setShowAddEndpoint(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Add Endpoint
                </Button>
              </div>

              {loading ? (
                <div className="text-center py-12 text-gray-500">Loading endpoints...</div>
              ) : endpoints.length === 0 ? (
                <div className="text-center py-12">
                  <Route className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-500 mb-4">No endpoints defined yet</p>
                  <p className="text-sm text-gray-400">
                    Click "Add Endpoint" to create your first endpoint
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {endpoints.map((endpoint) => (
                    <div
                      key={endpoint.id}
                      className="border border-gray-200 rounded-lg p-4 hover:border-primary-300 transition-colors cursor-pointer hover:shadow-md"
                      onClick={() => setEditingEndpoint(endpoint)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3">
                            <span className={`text-xs font-medium px-2 py-1 rounded ${
                              endpoint.method === 'GET' ? 'bg-green-100 text-green-700' :
                              endpoint.method === 'POST' ? 'bg-blue-100 text-blue-700' :
                              endpoint.method === 'PUT' ? 'bg-yellow-100 text-yellow-700' :
                              endpoint.method === 'PATCH' ? 'bg-orange-100 text-orange-700' :
                              endpoint.method === 'DELETE' ? 'bg-red-100 text-red-700' :
                              'bg-gray-100 text-gray-700'
                            }`}>
                              {endpoint.method}
                            </span>
                            <code className="text-sm font-mono text-gray-800">{endpoint.path}</code>
                          </div>
                          {endpoint.description && (
                            <p className="text-sm text-gray-600 mt-2">{endpoint.description}</p>
                          )}
                          <div className="mt-2 flex items-center gap-3 text-sm text-gray-500">
                            {endpoint.parameters?.length > 0 && (
                              <span>{endpoint.parameters.length} parameter(s)</span>
                            )}
                            {endpoint.response_schema && (
                              <span>→ {endpoint.response_schema}</span>
                            )}
                            {endpoint.status_code && (
                              <span className="text-xs px-1.5 py-0.5 bg-gray-100 rounded">
                                {endpoint.status_code}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t bg-gray-50 flex justify-end">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>

      {/* Add modals */}
      {showAddSchema && (
        <AddSchemaModal
          projectId={projectId}
          serviceId={service.id}
          onClose={() => setShowAddSchema(false)}
          onSuccess={handleSchemaAdded}
        />
      )}

      {showAddFunction && (
        <AddFunctionModal
          projectId={projectId}
          serviceId={service.id}
          onClose={() => setShowAddFunction(false)}
          onSuccess={handleFunctionAdded}
        />
      )}

      {showAddEndpoint && (
        <AddEndpointModal
          projectId={projectId}
          serviceId={service.id}
          availableDependencies={dependencies}
          availableSchemas={schemas}
          onClose={() => setShowAddEndpoint(false)}
          onSuccess={handleEndpointAdded}
        />
      )}

      {/* Edit modals */}
      {editingSchema && (
        <AddSchemaModal
          projectId={projectId}
          serviceId={service.id}
          initialData={editingSchema}
          onClose={() => setEditingSchema(null)}
          onSuccess={() => {
            setEditingSchema(null);
            fetchTabData();
          }}
        />
      )}

      {editingFunction && (
        <AddFunctionModal
          projectId={projectId}
          serviceId={service.id}
          initialData={editingFunction}
          onClose={() => setEditingFunction(null)}
          onSuccess={() => {
            setEditingFunction(null);
            fetchTabData();
          }}
        />
      )}

      {editingEndpoint && (
        <AddEndpointModal
          projectId={projectId}
          serviceId={service.id}
          availableDependencies={dependencies}
          availableSchemas={schemas}
          initialData={editingEndpoint}
          onClose={() => setEditingEndpoint(null)}
          onSuccess={() => {
            setEditingEndpoint(null);
            fetchTabData();
          }}
        />
      )}
    </div>
  );
}

export default ServiceDetailModal;
