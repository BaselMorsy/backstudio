import { useState, useEffect } from 'react';
import { FileJson, Download, Copy, Check } from 'lucide-react';
import { projectAPI } from '../../services/api';
import { getProjectStats, copyToClipboard } from '../../utils/helpers';
import Button from '../common/Button';

function ProjectStateTab({ projectId, project }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchState();
  }, [projectId]);

  const fetchState = async () => {
    try {
      setLoading(true);
      const response = await projectAPI.getState(projectId);
      setState(response.data);
    } catch (error) {
      console.error('Failed to fetch project state:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    const success = await copyToClipboard(JSON.stringify(state, null, 2));
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${project.name}-state.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  if (loading) {
    return <div className="text-center py-10">Loading...</div>;
  }

  const stats = getProjectStats(state);

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-3xl font-bold text-primary-600">{stats.models}</div>
          <div className="text-sm text-gray-600">Data Models</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-3xl font-bold text-green-600">{stats.services}</div>
          <div className="text-sm text-gray-600">Services</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-3xl font-bold text-blue-600">{stats.endpoints}</div>
          <div className="text-sm text-gray-600">API Endpoints</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-3xl font-bold text-purple-600">{stats.dependencies}</div>
          <div className="text-sm text-gray-600">Dependencies</div>
        </div>
      </div>

      {/* JSON State Viewer */}
      <div className="bg-white rounded-lg shadow">
        <div className="flex justify-between items-center p-4 border-b">
          <div className="flex items-center gap-2">
            <FileJson className="w-5 h-5 text-gray-600" />
            <h2 className="text-xl font-bold text-gray-800">Project State (JSON)</h2>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={handleCopy}
              className="flex items-center gap-2"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copied ? 'Copied!' : 'Copy'}
            </Button>
            <Button onClick={handleDownload} className="flex items-center gap-2">
              <Download className="w-4 h-4" />
              Download JSON
            </Button>
          </div>
        </div>

        <div className="p-4">
          <pre className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-[600px] text-sm">
            <code className="text-gray-300">{JSON.stringify(state, null, 2)}</code>
          </pre>
        </div>
      </div>

      {/* Checksum */}
      {state?.checksum && (
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <div className="text-sm font-medium text-gray-700 mb-1">Checksum (SHA-256)</div>
          <code className="text-xs text-gray-600 break-all">{state.checksum}</code>
        </div>
      )}
    </div>
  );
}

export default ProjectStateTab;
