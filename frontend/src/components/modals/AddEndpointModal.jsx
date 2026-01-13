import { useState, useEffect } from 'react';
import { X, Save, Plus, Trash2 } from 'lucide-react';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import { endpointAPI, schemaAPI } from '../../services/api';
import { HTTP_METHODS, PARAM_LOCATIONS, PYTHON_TYPES } from '../../utils/constants';

function AddEndpointModal({ projectId, serviceId, initialData, onClose, onSuccess, availableDependencies = [], availableSchemas = [] }) {
  const toast = useToast();
  const isEditMode = !!initialData;

  // Parse parameter type to determine type_category
  const parseParameterType = (typeString) => {
    const type_category = PYTHON_TYPES.includes(typeString) ? 'primitive' : 'synthetic';
    return type_category;
  };

  // Process initial data parameters
  const processInitialParameters = (parameters) => {
    return parameters.map(param => ({
      ...param,
      type_category: param.type_category || parseParameterType(param.type || 'str'),
    }));
  };

  const [formData, setFormData] = useState(
    initialData
      ? {
          ...initialData,
          tags: Array.isArray(initialData.tags) ? initialData.tags : [],
          parameters: processInitialParameters(initialData.parameters || []),
          middlewares: Array.isArray(initialData.middlewares) ? initialData.middlewares : [],
          dependencies: Array.isArray(initialData.dependencies) ? initialData.dependencies : [],
          providers: Array.isArray(initialData.providers)
            ? initialData.providers.map(p => ({ dependency_id: p.dependency_id }))  // Clean up to only include dependency_id
            : [],
        }
      : {
          path: '',
          method: 'GET',
          function_name: '',
          summary: '',
          description: '',
          tags: [],
          parameters: [],
          request_schema: '',
          response_schema: '',
          status_code: 200,
          middlewares: [],
          dependencies: [],
          providers: [],
        }
  );
  const [saving, setSaving] = useState(false);
  const [newTag, setNewTag] = useState('');
  const [localAvailableSchemas, setLocalAvailableSchemas] = useState([]);

  // Fetch available schemas for type selection
  useEffect(() => {
    const fetchSchemas = async () => {
      try {
        const response = await schemaAPI.getAll(projectId, serviceId);
        setLocalAvailableSchemas(response.data || []);
      } catch (error) {
        console.error('Failed to fetch schemas:', error);
      }
    };
    fetchSchemas();
  }, [projectId, serviceId]);

  const handleAddParameter = () => {
    setFormData({
      ...formData,
      parameters: [
        ...formData.parameters,
        { name: '', location: 'query', type: 'str', type_category: 'primitive', required: false, description: '' },
      ],
    });
  };

  const handleUpdateParameter = (index, param) => {
    const newParams = [...formData.parameters];
    newParams[index] = param;
    setFormData({ ...formData, parameters: newParams });
  };

  const handleRemoveParameter = (index) => {
    const newParams = formData.parameters.filter((_, i) => i !== index);
    setFormData({ ...formData, parameters: newParams });
  };

  const handleAddTag = () => {
    if (newTag.trim() && !formData.tags.includes(newTag.trim())) {
      setFormData({ ...formData, tags: [...formData.tags, newTag.trim()] });
      setNewTag('');
    }
  };

  const handleRemoveTag = (tagToRemove) => {
    setFormData({ ...formData, tags: formData.tags.filter(tag => tag !== tagToRemove) });
  };

  const handleAddProvider = () => {
    setFormData({
      ...formData,
      providers: [
        ...formData.providers,
        { dependency_id: '' }
      ]
    });
  };

  const handleUpdateProviderBinding = (index, binding) => {
    const newBindings = [...formData.providers];
    newBindings[index] = binding;
    setFormData({ ...formData, providers: newBindings });
  };

  const handleRemoveProviderBinding = (index) => {
    const newBindings = formData.providers.filter((_, i) => i !== index);
    setFormData({ ...formData, providers: newBindings });
  };

  const validateVariableName = (name) => {
    if (!name) return 'Variable name is required';
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)) {
      return 'Must be a valid Python identifier';
    }

    // Check for conflicts with path/query params
    const allParamNames = formData.parameters.map(p => p.name);
    if (allParamNames.includes(name)) {
      return 'Conflicts with existing parameter name';
    }

    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.path.trim()) {
      toast.showWarning('Endpoint path is required');
      return;
    }

    if (!formData.function_name.trim()) {
      toast.showWarning('Function name is required');
      return;
    }

    // Validate provider bindings
    for (const binding of formData.providers) {
      if (!binding.dependency_id) {
        toast.showWarning('All provider bindings must have a dependency selected');
        return;
      }
    }

    // Remove type_category from parameters before sending (frontend-only field)
    const processedParameters = formData.parameters.map(param => {
      const { type_category, ...rest } = param;
      return rest;
    });

    const payload = {
      ...formData,
      parameters: processedParameters,
    };

    // DEBUG: Log the full payload including providers
    console.log('=== ENDPOINT PAYLOAD DEBUG ===');
    console.log('Full payload:', JSON.stringify(payload, null, 2));
    console.log('Providers:', payload.providers);
    console.log('==============================');

    try {
      setSaving(true);
      if (isEditMode) {
        await endpointAPI.update(projectId, serviceId, initialData.id, payload);
        toast.showSuccess('Endpoint updated successfully');
      } else {
        await endpointAPI.create(projectId, serviceId, payload);
        toast.showSuccess('Endpoint created successfully');
      }
      onSuccess();
    } catch (error) {
      console.error(`Failed to ${isEditMode ? 'update' : 'create'} endpoint:`, error);
      toast.showError(error.response?.data?.detail || `Failed to ${isEditMode ? 'update' : 'create'} endpoint`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-800">
            {isEditMode ? 'Edit API Endpoint' : 'Add API Endpoint'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-1">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Method *
              </label>
              <select
                value={formData.method}
                onChange={(e) => setFormData({ ...formData, method: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                {HTTP_METHODS.map((method) => (
                  <option key={method} value={method}>
                    {method}
                  </option>
                ))}
              </select>
            </div>

            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Path *
              </label>
              <input
                type="text"
                value={formData.path}
                onChange={(e) => setFormData({ ...formData, path: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g., /users/{id}"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Function Name *
            </label>
            <input
              type="text"
              value={formData.function_name}
              onChange={(e) => setFormData({ ...formData, function_name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g., get_user"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Summary
            </label>
            <input
              type="text"
              value={formData.summary}
              onChange={(e) => setFormData({ ...formData, summary: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="Brief summary of endpoint"
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
              rows="2"
              placeholder="Detailed endpoint description..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Tags
            </label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTag())}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="Add a tag (press Enter)"
              />
              <Button type="button" size="sm" onClick={handleAddTag}>
                Add
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {formData.tags.map((tag, index) => (
                <span key={index} className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-primary-100 text-primary-800">
                  {tag}
                  <button
                    type="button"
                    onClick={() => handleRemoveTag(tag)}
                    className="ml-2 hover:text-primary-900"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Request Schema
              </label>
              <input
                type="text"
                value={formData.request_schema}
                onChange={(e) => setFormData({ ...formData, request_schema: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g., UserCreate"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Response Schema
              </label>
              <input
                type="text"
                value={formData.response_schema}
                onChange={(e) => setFormData({ ...formData, response_schema: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g., UserResponse"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Status Code
              </label>
              <input
                type="number"
                value={formData.status_code}
                onChange={(e) => setFormData({ ...formData, status_code: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="200"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Middlewares (Guards)
            </label>
            <div className="space-y-2">
              {availableDependencies.filter(d => d.type === 'guard').map((dep) => (
                <label key={dep.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={formData.middlewares.includes(dep.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setFormData({ ...formData, middlewares: [...formData.middlewares, dep.id] });
                      } else {
                        setFormData({ ...formData, middlewares: formData.middlewares.filter(id => id !== dep.id) });
                      }
                    }}
                    className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-sm">{dep.name}</span>
                </label>
              ))}
              {availableDependencies.filter(d => d.type === 'guard').length === 0 && (
                <p className="text-sm text-gray-500">No guards available</p>
              )}
            </div>
          </div>

          <div className="border-t pt-4">
            <div className="flex items-center justify-between mb-3">
              <label className="block text-sm font-medium text-gray-700">
                Provider Dependencies
              </label>
              <button
                type="button"
                onClick={handleAddProvider}
                className="flex items-center gap-1 px-3 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700"
              >
                <Plus className="w-4 h-4" />
                Add Provider
              </button>
            </div>

            {formData.providers.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">No providers used</p>
            ) : (
              <div className="space-y-3">
                {formData.providers.map((binding, index) => {
                  const provider = availableDependencies.find(d => d.id === binding.dependency_id);
                  const displayType = provider?.return_field
                    ? `${provider.return_type}.${provider.return_field}`
                    : provider?.return_type || 'Unknown';

                  return (
                    <div key={index} className="border border-gray-200 rounded-lg p-3">
                      <div className="flex items-start gap-2">
                        <div className="flex-1">
                          <label className="block text-xs font-medium text-gray-600 mb-1">
                            Provider Function
                          </label>
                          <select
                            value={binding.dependency_id}
                            onChange={(e) => handleUpdateProviderBinding(index, {
                              dependency_id: e.target.value
                            })}
                            className="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-primary-500"
                          >
                            <option value="">Select provider...</option>
                            {availableDependencies.filter(d => d.type === 'provider').map((provider) => (
                              <option key={provider.id} value={provider.id}>
                                {provider.name} → {provider.return_field ? `${provider.return_type}.${provider.return_field}` : provider.return_type || 'None'}
                              </option>
                            ))}
                          </select>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleRemoveProviderBinding(index)}
                          className="mt-5 p-1.5 text-red-600 hover:bg-red-50 rounded"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>

                      {binding.dependency_id && (
                        <div className="text-xs text-gray-500 mt-2">
                          Returns: {displayType}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="block text-sm font-medium text-gray-700">
                Parameters
              </label>
              <Button type="button" size="sm" onClick={handleAddParameter}>
                <Plus className="w-4 h-4 mr-1" />
                Add Parameter
              </Button>
            </div>

            <div className="space-y-3">
              {formData.parameters.map((param, index) => (
                <div key={index} className="border border-gray-200 rounded-lg p-4">
                  {/* Parameter name and delete button */}
                  <div className="flex gap-3 mb-3">
                    <input
                      type="text"
                      value={param.name}
                      onChange={(e) =>
                        handleUpdateParameter(index, { ...param, name: e.target.value })
                      }
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                      placeholder="Parameter name"
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveParameter(index)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="Remove parameter"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Location dropdown */}
                  <div className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Location
                    </label>
                    <select
                      value={param.location}
                      onChange={(e) =>
                        handleUpdateParameter(index, { ...param, location: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                    >
                      {PARAM_LOCATIONS.map((loc) => (
                        <option key={loc} value={loc}>
                          {loc}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Type category radio buttons */}
                  <div className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-2">
                      Type Category
                    </label>
                    <div className="flex gap-4">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name={`param-type-category-${index}`}
                          value="primitive"
                          checked={(param.type_category || 'primitive') === 'primitive'}
                          onChange={(e) =>
                            handleUpdateParameter(index, {
                              ...param,
                              type_category: 'primitive',
                              type: 'str',
                            })
                          }
                          className="text-primary-600 focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700">Primitive Type</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name={`param-type-category-${index}`}
                          value="synthetic"
                          checked={(param.type_category || 'primitive') === 'synthetic'}
                          onChange={(e) =>
                            handleUpdateParameter(index, {
                              ...param,
                              type_category: 'synthetic',
                              type: localAvailableSchemas[0]?.name || '',
                            })
                          }
                          className="text-primary-600 focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700">Synthetic Type</span>
                      </label>
                    </div>
                  </div>

                  {/* Type dropdown */}
                  <div className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Type
                    </label>
                    <select
                      value={param.type}
                      onChange={(e) =>
                        handleUpdateParameter(index, { ...param, type: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                    >
                      {(param.type_category || 'primitive') === 'primitive'
                        ? PYTHON_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))
                        : localAvailableSchemas.map((schema) => (
                            <option key={schema.id} value={schema.name}>
                              {schema.name}
                            </option>
                          ))}
                      {(param.type_category || 'primitive') === 'synthetic' &&
                        localAvailableSchemas.length === 0 && (
                          <option value="">No schemas available</option>
                        )}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      type="text"
                      value={param.description || ''}
                      onChange={(e) =>
                        handleUpdateParameter(index, { ...param, description: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                      placeholder="Description (optional)"
                    />
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id={`required-${index}`}
                        checked={param.required}
                        onChange={(e) =>
                          handleUpdateParameter(index, { ...param, required: e.target.checked })
                        }
                        className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      <label htmlFor={`required-${index}`} className="text-sm text-gray-700">
                        Required
                      </label>
                    </div>
                  </div>
                </div>
              ))}

              {formData.parameters.length === 0 && (
                <p className="text-sm text-gray-500 text-center py-4">
                  No parameters added yet. Click "Add Parameter" to add parameters to this endpoint.
                </p>
              )}
            </div>
          </div>
        </form>

        <div className="px-6 py-4 border-t bg-gray-50 flex gap-3">
          <Button type="submit" onClick={handleSubmit} disabled={saving}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Endpoint' : 'Create Endpoint')}
          </Button>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

export default AddEndpointModal;
