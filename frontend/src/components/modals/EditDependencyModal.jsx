import { useState, useEffect } from 'react';
import { X, Save, Plus, Trash2 } from 'lucide-react';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import { dependencyAPI, modelAPI } from '../../services/api';
import { DEPENDENCY_TYPES, DEPENDENCY_SCOPES, FUNCTION_PARAM_TYPES } from '../../utils/constants';

function EditDependencyModal({ dependency, projectId, onClose, onSuccess }) {
  const toast = useToast();
  // Parse return type to determine type_category
  const parseReturnType = (typeString) => {
    if (!typeString) return 'primitive';
    const type_category = FUNCTION_PARAM_TYPES.includes(typeString) ? 'primitive' : 'synthetic';
    return type_category;
  };

  // Process initial parameters
  const processInitialParameters = (parameters) => {
    return parameters.map(param => ({
      ...param,
      type_category: param.type_category || (FUNCTION_PARAM_TYPES.includes(param.type || 'str') ? 'primitive' : 'synthetic'),
    }));
  };

  const [formData, setFormData] = useState({
    name: dependency.name,
    type: dependency.type,
    description: dependency.description || '',
    scope: dependency.scope,
    function_name: dependency.function_name,
    return_type: dependency.return_type || '',
    return_field: dependency.return_field || '',
    return_type_category: parseReturnType(dependency.return_type),
    parameters: processInitialParameters(dependency.parameters || []),
    is_async: dependency.is_async ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [availableModels, setAvailableModels] = useState([]);

  // Fetch available models for type selection
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await modelAPI.getAll(projectId);
        setAvailableModels(response.data || []);
      } catch (error) {
        console.error('Failed to fetch models:', error);
      }
    };
    fetchModels();
  }, [projectId]);

  const handleAddParameter = () => {
    setFormData({
      ...formData,
      parameters: [
        ...formData.parameters,
        { name: '', type: 'str', type_category: 'primitive', required: true, description: '' },
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

    if (!formData.name.trim() || !formData.function_name.trim()) {
      toast.showWarning('Name and function name are required');
      return;
    }

    // Remove type_category from parameters and return_type_category before sending
    const processedParameters = formData.parameters.map(param => {
      const { type_category, ...rest } = param;
      return rest;
    });

    const { return_type_category, ...restFormData } = formData;

    try {
      setSaving(true);
      await dependencyAPI.update(projectId, dependency.id, {
        ...restFormData,
        parameters: processedParameters,
      });
      toast.showSuccess('Dependency updated successfully');
      onSuccess();
    } catch (error) {
      console.error('Failed to update dependency:', error);
      toast.showError(error.response?.data?.detail || 'Failed to update dependency');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b flex items-center justify-between sticky top-0 bg-white z-10">
          <h2 className="text-xl font-bold text-gray-800">Edit Dependency</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="get_current_user"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Type *
            </label>
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {DEPENDENCY_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Scope *
            </label>
            <select
              value={formData.scope}
              onChange={(e) => setFormData({ ...formData, scope: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {DEPENDENCY_SCOPES.map((scope) => (
                <option key={scope.value} value={scope.value}>
                  {scope.label}
                </option>
              ))}
            </select>
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
              placeholder="get_current_user"
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
                        return_type: availableModels[0]?.name || '',
                      })
                    }
                    className="text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-sm text-gray-700">Data Model</span>
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
                  : availableModels.map((model) => (
                      <option key={model.id} value={model.name}>
                        {model.name}
                      </option>
                    ))}
                {(formData.return_type_category || 'primitive') === 'synthetic' &&
                  availableModels.length === 0 && (
                    <option value="">No models available</option>
                  )}
              </select>
            </div>

            {/* Field Selector - only show for Data Model return types */}
            {(formData.return_type_category || 'primitive') === 'synthetic' && formData.return_type && (
              <div className="mb-3">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Return Field (Optional)
                </label>
                <select
                  value={formData.return_field || ''}
                  onChange={(e) => setFormData({ ...formData, return_field: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                >
                  <option value="">Whole Object</option>
                  {availableModels
                    .find(m => m.name === formData.return_type)?.fields
                    ?.map((field) => (
                      <option key={field.name} value={field.name}>
                        {field.name} ({field.type})
                      </option>
                    ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Select a field to extract (e.g., 'id' returns User.id instead of User object)
                </p>
              </div>
            )}
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
              placeholder="Description of dependency..."
            />
          </div>

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

          {/* Parameters Section */}
          <div className="border-t pt-4">
            <div className="flex items-center justify-between mb-3">
              <label className="block text-sm font-medium text-gray-700">
                Parameters
              </label>
              <button
                type="button"
                onClick={handleAddParameter}
                className="flex items-center gap-1 px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                <Plus className="w-4 h-4" />
                Add Parameter
              </button>
            </div>

            {formData.parameters.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">No parameters defined</p>
            ) : (
              <div className="space-y-3">
                {formData.parameters.map((param, index) => (
                  <div key={index} className="border border-gray-200 rounded-lg p-3 space-y-2">
                    <div className="flex items-start gap-2">
                      <div className="flex-1">
                        <input
                          type="text"
                          value={param.name}
                          onChange={(e) =>
                            handleUpdateParameter(index, { ...param, name: e.target.value })
                          }
                          className="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-primary-500"
                          placeholder="parameter_name"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveParameter(index)}
                        className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>

                    {/* Type Category */}
                    <div className="flex gap-3 text-xs">
                      <label className="flex items-center gap-1">
                        <input
                          type="radio"
                          name={`param-type-${index}`}
                          checked={param.type_category === 'primitive'}
                          onChange={() =>
                            handleUpdateParameter(index, {
                              ...param,
                              type_category: 'primitive',
                              type: 'str',
                            })
                          }
                          className="text-primary-600"
                        />
                        <span>Primitive</span>
                      </label>
                      <label className="flex items-center gap-1">
                        <input
                          type="radio"
                          name={`param-type-${index}`}
                          checked={param.type_category === 'synthetic'}
                          onChange={() =>
                            handleUpdateParameter(index, {
                              ...param,
                              type_category: 'synthetic',
                              type: availableModels[0]?.name || '',
                            })
                          }
                          className="text-primary-600"
                        />
                        <span>Model</span>
                      </label>
                    </div>

                    {/* Type Selection */}
                    <select
                      value={param.type}
                      onChange={(e) =>
                        handleUpdateParameter(index, { ...param, type: e.target.value })
                      }
                      className="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-primary-500"
                    >
                      {param.type_category === 'primitive'
                        ? FUNCTION_PARAM_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))
                        : availableModels.map((model) => (
                            <option key={model.id} value={model.name}>
                              {model.name}
                            </option>
                          ))}
                    </select>

                    {/* Required Checkbox */}
                    <label className="flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={param.required}
                        onChange={(e) =>
                          handleUpdateParameter(index, { ...param, required: e.target.checked })
                        }
                        className="rounded border-gray-300 text-primary-600"
                      />
                      <span className="text-gray-700">Required</span>
                    </label>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex gap-3 pt-4 border-t sticky bottom-0 bg-white">
            <Button type="submit" disabled={saving}>
              <Save className="w-4 h-4 mr-2" />
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default EditDependencyModal;
