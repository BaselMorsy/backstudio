import { useState, useEffect } from 'react';
import { X, Save, Plus, Trash2 } from 'lucide-react';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import { functionAPI, schemaAPI } from '../../services/api';
import { FUNCTION_PARAM_TYPES } from '../../utils/constants';

function AddFunctionModal({ projectId, serviceId, initialData, onClose, onSuccess }) {
  const toast = useToast();
  const isEditMode = !!initialData;

  // Parse parameter type to determine type_category
  const parseParameterType = (typeString) => {
    const type_category = FUNCTION_PARAM_TYPES.includes(typeString) ? 'primitive' : 'synthetic';
    return type_category;
  };

  // Parse return type to determine type_category
  const parseReturnType = (typeString) => {
    if (!typeString) return 'primitive';
    const type_category = FUNCTION_PARAM_TYPES.includes(typeString) ? 'primitive' : 'synthetic';
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
          parameters: processInitialParameters(initialData.parameters || []),
          return_type_category: parseReturnType(initialData.return_type),
        }
      : {
          name: '',
          description: '',
          parameters: [],
          return_type: '',
          return_type_category: 'primitive',
          is_async: true,
        }
  );
  const [saving, setSaving] = useState(false);
  const [availableSchemas, setAvailableSchemas] = useState([]);

  // Fetch available schemas for type selection
  useEffect(() => {
    const fetchSchemas = async () => {
      try {
        const response = await schemaAPI.getAll(projectId, serviceId);
        setAvailableSchemas(response.data || []);
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
        { name: '', type: 'str', type_category: 'primitive', required: false, description: '' },
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

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name.trim()) {
      toast.showWarning('Function name is required');
      return;
    }

    // Remove type_category from parameters before sending (frontend-only field)
    const processedParameters = formData.parameters.map(param => {
      const { type_category, ...rest } = param;
      return rest;
    });

    // Remove return_type_category (frontend-only field)
    const { return_type_category, ...restFormData } = formData;

    const payload = {
      ...restFormData,
      parameters: processedParameters,
    };

    try {
      setSaving(true);
      if (isEditMode) {
        await functionAPI.update(projectId, serviceId, initialData.id, payload);
        toast.showSuccess('Function updated successfully');
      } else {
        await functionAPI.create(projectId, serviceId, payload);
        toast.showSuccess('Function created successfully');
      }
      onSuccess();
    } catch (error) {
      console.error(`Failed to ${isEditMode ? 'update' : 'create'} function:`, error);
      toast.showError(error.response?.data?.detail || `Failed to ${isEditMode ? 'update' : 'create'} function`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-800">
            {isEditMode ? 'Edit Service Function' : 'Add Service Function'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Function Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g., create_user"
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
              placeholder="Function description..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Return Type
            </label>

            {/* Return type category radio buttons */}
            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-2">
                Type Category
              </label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="return-type-category"
                    value="primitive"
                    checked={(formData.return_type_category || 'primitive') === 'primitive'}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        return_type_category: 'primitive',
                        return_type: 'str',
                      })
                    }
                    className="text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-sm text-gray-700">Primitive Type</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="return-type-category"
                    value="synthetic"
                    checked={(formData.return_type_category || 'primitive') === 'synthetic'}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        return_type_category: 'synthetic',
                        return_type: availableSchemas[0]?.name || '',
                      })
                    }
                    className="text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-sm text-gray-700">Synthetic Type</span>
                </label>
              </div>
            </div>

            {/* Return type dropdown */}
            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Type
              </label>
              <select
                value={formData.return_type}
                onChange={(e) => setFormData({ ...formData, return_type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
              >
                <option value="">None</option>
                {(formData.return_type_category || 'primitive') === 'primitive'
                  ? FUNCTION_PARAM_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))
                  : availableSchemas.map((schema) => (
                      <option key={schema.id} value={schema.name}>
                        {schema.name}
                      </option>
                    ))}
                {(formData.return_type_category || 'primitive') === 'synthetic' &&
                  availableSchemas.length === 0 && (
                    <option value="">No schemas available</option>
                  )}
              </select>
            </div>

            {/* Async checkbox */}
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_async"
                checked={formData.is_async}
                onChange={(e) => setFormData({ ...formData, is_async: e.target.checked })}
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label htmlFor="is_async" className="text-sm text-gray-700">
                Async function
              </label>
            </div>
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
                  {/* Parameter name */}
                  <div className="flex gap-3 mb-3">
                    <input
                      type="text"
                      value={param.name}
                      onChange={(e) =>
                        handleUpdateParameter(index, { ...param, name: e.target.value })
                      }
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
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
                              type: availableSchemas[0]?.name || '',
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
                        ? FUNCTION_PARAM_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))
                        : availableSchemas.map((schema) => (
                            <option key={schema.id} value={schema.name}>
                              {schema.name}
                            </option>
                          ))}
                      {(param.type_category || 'primitive') === 'synthetic' &&
                        availableSchemas.length === 0 && (
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
                  No parameters added yet. Click "Add Parameter" to add parameters to this function.
                </p>
              )}
            </div>
          </div>
        </form>

        <div className="px-6 py-4 border-t bg-gray-50 flex gap-3">
          <Button type="submit" onClick={handleSubmit} disabled={saving}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Function' : 'Create Function')}
          </Button>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

export default AddFunctionModal;
