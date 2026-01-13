import { useState, useEffect } from 'react';
import { Database, Code, Shield, Save } from 'lucide-react';
import { configAPI } from '../../services/api';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import { DATABASE_TYPES, AUTH_STRATEGIES, JWT_ALGORITHMS, FRAMEWORKS } from '../../utils/constants';

function ConfigurationTab({ projectId, project, onFrameworkChange }) {
  const toast = useToast();
  const [dbConfig, setDbConfig] = useState(null);
  const [fwConfig, setFwConfig] = useState(null);
  const [secConfig, setSecConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState('framework');
  const [saving, setSaving] = useState(false);

  // Form states
  const [dbForm, setDbForm] = useState({
    type: 'postgresql',
    host: 'localhost',
    port: 5432,
    database_name: '',
    username: '',
    use_env_vars: true,
    pool_size: 10,
    echo: false,
  });

  const [fwForm, setFwForm] = useState({
    language: 'python',
    framework: 'fastapi',
    version: '',
    use_async: true,
    enable_cors: true,
    api_prefix: '/api',
  });

  const [secForm, setSecForm] = useState({
    auth_strategy: 'jwt',
    jwt_secret_env_var: 'JWT_SECRET',
    jwt_algorithm: 'HS256',
    jwt_expiration_minutes: 30,
    enable_https: true,
    allowed_origins: [],
    rate_limit_enabled: true,
    rate_limit_requests: 100,
    rate_limit_window_minutes: 1,
  });

  const [originInput, setOriginInput] = useState('');

  useEffect(() => {
    fetchConfigs();
  }, [projectId]);

  const fetchConfigs = async () => {
    try {
      setLoading(true);
      try {
        const db = await configAPI.database.get(projectId);
        setDbConfig(db.data);
        setDbForm(db.data);
      } catch (error) {
        // Config doesn't exist yet
      }
      try {
        const fw = await configAPI.framework.get(projectId);
        setFwConfig(fw.data);
        setFwForm(fw.data);
      } catch (error) {
        // Config doesn't exist yet
      }
      try {
        const sec = await configAPI.security.get(projectId);
        setSecConfig(sec.data);
        setSecForm(sec.data);
      } catch (error) {
        // Config doesn't exist yet
      }
    } finally {
      setLoading(false);
    }
  };

  const saveDatabaseConfig = async () => {
    if (!dbForm.database_name.trim()) {
      toast.showWarning('Database name is required');
      return;
    }

    try {
      setSaving(true);
      const method = dbConfig ? configAPI.database.update : configAPI.database.create;
      const response = await method(projectId, dbForm);
      setDbConfig(response.data);
      toast.showSuccess('Database configuration saved!');
    } catch (error) {
      console.error('Failed to save database config:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to save configuration';
      toast.showError(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const saveFrameworkConfig = async () => {
    if (!fwForm.language.trim() || !fwForm.framework.trim()) {
      toast.showWarning('Language and framework are required');
      return;
    }

    try {
      setSaving(true);
      const method = fwConfig ? configAPI.framework.update : configAPI.framework.create;
      const response = await method(projectId, fwForm);
      setFwConfig(response.data);
      toast.showSuccess('Framework configuration saved!');
      // Notify parent to refresh project data
      if (onFrameworkChange) {
        onFrameworkChange();
      }
    } catch (error) {
      console.error('Failed to save framework config:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to save configuration';
      toast.showError(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const saveSecurityConfig = async () => {
    try {
      setSaving(true);
      const method = secConfig ? configAPI.security.update : configAPI.security.create;
      const response = await method(projectId, secForm);
      setSecConfig(response.data);
      toast.showSuccess('Security configuration saved!');
    } catch (error) {
      console.error('Failed to save security config:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to save configuration';
      toast.showError(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const addOrigin = () => {
    if (originInput.trim() && !secForm.allowed_origins.includes(originInput.trim())) {
      setSecForm({
        ...secForm,
        allowed_origins: [...secForm.allowed_origins, originInput.trim()],
      });
      setOriginInput('');
    }
  };

  const removeOrigin = (origin) => {
    setSecForm({
      ...secForm,
      allowed_origins: secForm.allowed_origins.filter((o) => o !== origin),
    });
  };

  const getDefaultPort = (type) => {
    const ports = {
      postgresql: 5432,
      mysql: 3306,
      sqlite: null,
      mongodb: 27017,
      redis: 6379,
    };
    return ports[type] || null;
  };

  if (loading) {
    return <div className="text-center py-10">Loading configuration...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-2xl font-bold mb-6">Project Configuration</h2>

        {/* Section tabs */}
        <div className="flex gap-4 mb-6 border-b">
          <button
            onClick={() => setActiveSection('framework')}
            className={`pb-2 px-3 flex items-center gap-2 ${
              activeSection === 'framework'
                ? 'border-b-2 border-primary-600 text-primary-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <Code className="w-4 h-4" />
            Framework
          </button>
          <button
            onClick={() => setActiveSection('database')}
            className={`pb-2 px-3 flex items-center gap-2 ${
              activeSection === 'database'
                ? 'border-b-2 border-primary-600 text-primary-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <Database className="w-4 h-4" />
            Database
          </button>
          <button
            onClick={() => setActiveSection('security')}
            className={`pb-2 px-3 flex items-center gap-2 ${
              activeSection === 'security'
                ? 'border-b-2 border-primary-600 text-primary-600'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            <Shield className="w-4 h-4" />
            Security
          </button>
        </div>

        {/* Database Configuration */}
        {activeSection === 'database' && (
          <div className="space-y-4">
            {!fwConfig && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                <p className="text-sm text-yellow-800">
                  <strong>Note:</strong> Please configure the framework first in the Framework tab before setting up the database.
                </p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Database Type *
                </label>
                <select
                  value={dbForm.type}
                  onChange={(e) => {
                    const newType = e.target.value;
                    setDbForm({
                      ...dbForm,
                      type: newType,
                      port: getDefaultPort(newType),
                    });
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  {DATABASE_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type.toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Database Name *
                </label>
                <input
                  type="text"
                  value={dbForm.database_name}
                  onChange={(e) => setDbForm({ ...dbForm, database_name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="myapp_db"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Host
                </label>
                <input
                  type="text"
                  value={dbForm.host}
                  onChange={(e) => setDbForm({ ...dbForm, host: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="localhost"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Port
                </label>
                <input
                  type="number"
                  value={dbForm.port || ''}
                  onChange={(e) => setDbForm({ ...dbForm, port: e.target.value ? parseInt(e.target.value) : null })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="5432"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Username
                </label>
                <input
                  type="text"
                  value={dbForm.username}
                  onChange={(e) => setDbForm({ ...dbForm, username: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="db_user"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Pool Size
                </label>
                <input
                  type="number"
                  value={dbForm.pool_size}
                  onChange={(e) => setDbForm({ ...dbForm, pool_size: parseInt(e.target.value) || 10 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  min="1"
                  max="100"
                />
              </div>
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={dbForm.use_env_vars}
                  onChange={(e) => setDbForm({ ...dbForm, use_env_vars: e.target.checked })}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Use environment variables for credentials</span>
              </label>

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={dbForm.echo}
                  onChange={(e) => setDbForm({ ...dbForm, echo: e.target.checked })}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Echo SQL queries (debug mode)</span>
              </label>
            </div>

            <Button onClick={saveDatabaseConfig} disabled={saving} className="mt-4">
              <Save className="w-4 h-4 mr-2" />
              {saving ? 'Saving...' : 'Save Database Configuration'}
            </Button>
          </div>
        )}

        {/* Framework Configuration */}
        {activeSection === 'framework' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Framework
                </label>
                <input
                  type="text"
                  value="FastAPI"
                  readOnly
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-600 cursor-not-allowed"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Language
                </label>
                <input
                  type="text"
                  value="Python"
                  readOnly
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-600 cursor-not-allowed"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Version
                </label>
                <input
                  type="text"
                  value={fwForm.version}
                  onChange={(e) => setFwForm({ ...fwForm, version: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="0.104.1"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  API Prefix
                </label>
                <input
                  type="text"
                  value={fwForm.api_prefix}
                  onChange={(e) => setFwForm({ ...fwForm, api_prefix: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="/api"
                />
              </div>
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={fwForm.use_async}
                  onChange={(e) => setFwForm({ ...fwForm, use_async: e.target.checked })}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Use async/await patterns</span>
              </label>

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={fwForm.enable_cors}
                  onChange={(e) => setFwForm({ ...fwForm, enable_cors: e.target.checked })}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Enable CORS</span>
              </label>
            </div>

            <Button onClick={saveFrameworkConfig} disabled={saving} className="mt-4">
              <Save className="w-4 h-4 mr-2" />
              {saving ? 'Saving...' : 'Save Framework Configuration'}
            </Button>
          </div>
        )}

        {/* Security Configuration */}
        {activeSection === 'security' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Authentication Strategy *
                </label>
                <select
                  value={secForm.auth_strategy}
                  onChange={(e) => setSecForm({ ...secForm, auth_strategy: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  {AUTH_STRATEGIES.map((strategy) => (
                    <option key={strategy} value={strategy}>
                      {strategy.toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  JWT Algorithm
                </label>
                <select
                  value={secForm.jwt_algorithm}
                  onChange={(e) => setSecForm({ ...secForm, jwt_algorithm: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  {JWT_ALGORITHMS.map((algo) => (
                    <option key={algo} value={algo}>
                      {algo}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  JWT Secret Env Var
                </label>
                <input
                  type="text"
                  value={secForm.jwt_secret_env_var}
                  onChange={(e) => setSecForm({ ...secForm, jwt_secret_env_var: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="JWT_SECRET"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  JWT Expiration (minutes)
                </label>
                <input
                  type="number"
                  value={secForm.jwt_expiration_minutes}
                  onChange={(e) => setSecForm({ ...secForm, jwt_expiration_minutes: parseInt(e.target.value) || 30 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  min="1"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Rate Limit Requests
                </label>
                <input
                  type="number"
                  value={secForm.rate_limit_requests}
                  onChange={(e) => setSecForm({ ...secForm, rate_limit_requests: parseInt(e.target.value) || 100 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  min="1"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Rate Limit Window (minutes)
                </label>
                <input
                  type="number"
                  value={secForm.rate_limit_window_minutes}
                  onChange={(e) => setSecForm({ ...secForm, rate_limit_window_minutes: parseInt(e.target.value) || 1 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  min="1"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Allowed CORS Origins
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={originInput}
                  onChange={(e) => setOriginInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addOrigin()}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="https://example.com"
                />
                <Button onClick={addOrigin} variant="outline">
                  Add
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {secForm.allowed_origins.map((origin, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center gap-2 bg-gray-100 px-3 py-1 rounded-full text-sm"
                  >
                    {origin}
                    <button
                      onClick={() => removeOrigin(origin)}
                      className="text-red-600 hover:text-red-800"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={secForm.enable_https}
                  onChange={(e) => setSecForm({ ...secForm, enable_https: e.target.checked })}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Enforce HTTPS</span>
              </label>

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={secForm.rate_limit_enabled}
                  onChange={(e) => setSecForm({ ...secForm, rate_limit_enabled: e.target.checked })}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Enable Rate Limiting</span>
              </label>
            </div>

            <Button onClick={saveSecurityConfig} disabled={saving} className="mt-4">
              <Save className="w-4 h-4 mr-2" />
              {saving ? 'Saving...' : 'Save Security Configuration'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ConfigurationTab;
