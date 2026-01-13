import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Download, RefreshCw, Edit2, Check, X, Settings, Database, Package, Boxes, FolderTree, FileText } from 'lucide-react';
import { projectAPI } from '../services/api';
import { downloadFile } from '../utils/helpers';
import { useToast } from '../components/common/ToastContainer';
import ConfirmDialog from '../components/common/ConfirmDialog';
import Button from '../components/common/Button';
import DatabaseTab from '../components/tabs/DatabaseTab';
import ConfigurationTab from '../components/tabs/ConfigurationTab';
import DependenciesTab from '../components/tabs/DependenciesTab';
import ServicesTab from '../components/tabs/ServicesTab';
import StructurePreviewTab from '../components/tabs/StructurePreviewTab';
import ProjectStateTab from '../components/tabs/ProjectStateTab';

function ProjectPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('configuration');
  const [editingName, setEditingName] = useState(false);
  const [editingVersion, setEditingVersion] = useState(false);
  const [tempName, setTempName] = useState('');
  const [tempVersion, setTempVersion] = useState('');
  const [confirmDialog, setConfirmDialog] = useState(null);

  const tabs = [
    { id: 'configuration', label: 'Configuration', icon: Settings },
    { id: 'database', label: 'Database', icon: Database },
    { id: 'dependencies', label: 'Dependencies', icon: Package },
    { id: 'services', label: 'Services', icon: Boxes },
    { id: 'structure', label: 'Structure Preview', icon: FolderTree },
    { id: 'state', label: 'Project State', icon: FileText },
  ];

  useEffect(() => {
    fetchProject();
  }, [projectId]);

  const fetchProject = async () => {
    try {
      setLoading(true);
      const response = await projectAPI.getById(projectId);
      setProject(response.data);
      setTempName(response.data.name);
      setTempVersion(response.data.version);
    } catch (error) {
      console.error('Failed to fetch project:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to load project';
      toast.showError(errorMessage);
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveName = async () => {
    if (!tempName.trim()) {
      toast.showWarning('Project name cannot be empty');
      return;
    }

    try {
      const response = await projectAPI.update(projectId, { name: tempName });
      setProject(response.data);
      setEditingName(false);
      toast.showSuccess('Project name updated successfully');
    } catch (error) {
      console.error('Failed to update project name:', error);
      toast.showError(error.response?.data?.detail || 'Failed to update project name');
    }
  };

  const handleSaveVersion = async () => {
    if (!tempVersion.trim()) {
      toast.showWarning('Version cannot be empty');
      return;
    }

    try {
      const response = await projectAPI.update(projectId, { version: tempVersion });
      setProject(response.data);
      setEditingVersion(false);
      toast.showSuccess('Version updated successfully');
    } catch (error) {
      console.error('Failed to update version:', error);
      toast.showError(error.response?.data?.detail || 'Failed to update version');
    }
  };

  const handleSync = async () => {
    setConfirmDialog({
      type: 'sync',
      title: 'Sync Project',
      message: 'This will regenerate code files to match your current project specifications. Your project data will NOT be deleted. Continue?',
      confirmText: 'Sync',
      variant: 'warning'
    });
  };

  const handleConfirmSync = async () => {
    try {
      const response = await projectAPI.sync(projectId);
      toast.showSuccess(response.data.message || 'Project synchronized successfully!');
      // Note: We don't call fetchProject() because sync doesn't change project state,
      // it only updates generated code files
    } catch (error) {
      console.error('Failed to sync project:', error);
      const errorMsg = error.response?.data?.detail || 'Failed to sync project. You may need to Generate code first.';
      toast.showError(errorMsg);
    }
  };

  const handleGenerate = async () => {
    setConfirmDialog({
      type: 'generate',
      title: 'Generate Code',
      message: 'Generate code for this project? If code already exists, it will be overwritten.',
      confirmText: 'Generate',
      variant: 'warning'
    });
  };

  const handleConfirmGenerate = async () => {
    try {
      await projectAPI.generate(projectId, true);
      toast.showSuccess('Code generated successfully!');
      fetchProject();
    } catch (error) {
      if (error.response?.status === 409) {
        toast.showError('Code already exists. Use Sync to update existing code.');
      } else {
        console.error('Failed to generate code:', error);
        toast.showError(error.response?.data?.detail || 'Failed to generate code');
      }
    }
  };

  const handleDownload = async () => {
    try {
      const response = await projectAPI.download(projectId);
      downloadFile(response.data, `${project.name}.zip`);
      toast.showSuccess('Project downloaded successfully!');
    } catch (error) {
      if (error.response?.status === 404) {
        toast.showError('No generated code found. Please generate code first.');
      } else {
        console.error('Failed to download project:', error);
        toast.showError(error.response?.data?.detail || 'Failed to download project');
      }
    }
  };

  const handleConfirmAction = () => {
    if (confirmDialog?.type === 'sync') {
      handleConfirmSync();
    } else if (confirmDialog?.type === 'generate') {
      handleConfirmGenerate();
    }
    setConfirmDialog(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Loading project...</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Project not found</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Ribbon */}
      <div className="bg-white shadow-sm border-b sticky top-0 z-10">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/dashboard')}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                title="Back to Dashboard"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3">
                {editingName ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={tempName}
                      onChange={(e) => setTempName(e.target.value)}
                      className="px-2 py-1 border border-gray-300 rounded text-xl font-bold"
                      autoFocus
                      onKeyPress={(e) => e.key === 'Enter' && handleSaveName()}
                    />
                    <button
                      onClick={handleSaveName}
                      className="p-1 text-green-600 hover:bg-green-50 rounded"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => {
                        setEditingName(false);
                        setTempName(project.name);
                      }}
                      className="p-1 text-red-600 hover:bg-red-50 rounded"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <h1 className="text-xl font-bold text-gray-800">{project.name}</h1>
                    <button
                      onClick={() => setEditingName(true)}
                      className="p-1 text-gray-400 hover:text-gray-600"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                  </div>
                )}

                {editingVersion ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={tempVersion}
                      onChange={(e) => setTempVersion(e.target.value)}
                      className="px-2 py-1 border border-gray-300 rounded text-sm"
                      autoFocus
                      onKeyPress={(e) => e.key === 'Enter' && handleSaveVersion()}
                    />
                    <button
                      onClick={handleSaveVersion}
                      className="p-1 text-green-600 hover:bg-green-50 rounded"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => {
                        setEditingVersion(false);
                        setTempVersion(project.version);
                      }}
                      className="p-1 text-red-600 hover:bg-red-50 rounded"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500">v{project.version}</span>
                    <button
                      onClick={() => setEditingVersion(true)}
                      className="p-1 text-gray-400 hover:text-gray-600"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button variant="outline" onClick={handleSync} className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4" />
                Sync
              </Button>
              <Button variant="secondary" onClick={handleGenerate} className="flex items-center gap-2">
                <Save className="w-4 h-4" />
                Generate
              </Button>
              <Button onClick={handleDownload} className="flex items-center gap-2">
                <Download className="w-4 h-4" />
                Download ZIP
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white border-b">
        <div className="container mx-auto px-6">
          <div className="flex gap-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-6 py-3 font-medium transition-colors border-b-2 flex items-center gap-2 ${
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
      </div>

      {/* Tab Content */}
      <div className="container mx-auto px-6 py-6">
        {activeTab === 'configuration' && <ConfigurationTab projectId={projectId} project={project} onFrameworkChange={fetchProject} />}
        {activeTab === 'database' && <DatabaseTab projectId={projectId} project={project} />}
        {activeTab === 'dependencies' && <DependenciesTab projectId={projectId} />}
        {activeTab === 'services' && <ServicesTab projectId={projectId} />}
        {activeTab === 'structure' && <StructurePreviewTab projectId={projectId} />}
        {activeTab === 'state' && <ProjectStateTab projectId={projectId} project={project} />}
      </div>

      <ConfirmDialog
        isOpen={!!confirmDialog}
        title={confirmDialog?.title || ''}
        message={confirmDialog?.message || ''}
        confirmText={confirmDialog?.confirmText || 'Confirm'}
        variant={confirmDialog?.variant || 'danger'}
        onConfirm={handleConfirmAction}
        onCancel={() => setConfirmDialog(null)}
      />
    </div>
  );
}

export default ProjectPage;
