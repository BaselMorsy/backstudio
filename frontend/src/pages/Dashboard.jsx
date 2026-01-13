import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Grid3x3, List, Edit2, Trash2 } from 'lucide-react';
import { projectAPI } from '../services/api';
import { FRAMEWORKS } from '../utils/constants';
import { getFrameworkInfo, formatDate } from '../utils/helpers';
import { useToast } from '../components/common/ToastContainer';
import CreateProjectModal from '../components/modals/CreateProjectModal';
import ConfirmDialog from '../components/common/ConfirmDialog';
import Button from '../components/common/Button';
import StaticLogo from '../components/StaticLogo';

function Dashboard() {
  const navigate = useNavigate();
  const toast = useToast();
  const [projects, setProjects] = useState([]);
  const [filteredProjects, setFilteredProjects] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'list'
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  useEffect(() => {
    fetchProjects();
  }, []);

  useEffect(() => {
    filterProjects();
  }, [searchQuery, projects]);

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const response = await projectAPI.getAll();
      setProjects(response.data);
    } catch (error) {
      console.error('Failed to fetch projects:', error);
      toast.showError('Failed to load projects. Please refresh the page.');
    } finally {
      setLoading(false);
    }
  };

  const filterProjects = () => {
    if (!searchQuery.trim()) {
      setFilteredProjects(projects);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = projects.filter(
      (project) =>
        project.name.toLowerCase().includes(query) ||
        project.version.toLowerCase().includes(query) ||
        project.framework.toLowerCase().includes(query)
    );
    setFilteredProjects(filtered);
  };

  const handleDeleteProject = async () => {
    if (!deleteConfirm) return;

    const { projectId, projectName } = deleteConfirm;

    try {
      await projectAPI.delete(projectId);
      setProjects(projects.filter((p) => p.id !== projectId));
      toast.showSuccess(`Project "${projectName}" deleted successfully.`);
    } catch (error) {
      console.error('Failed to delete project:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to delete project. Please try again.';
      toast.showError(errorMessage);
    } finally {
      setDeleteConfirm(null);
    }
  };

  const handleProjectCreated = (newProject) => {
    setProjects([newProject, ...projects]);
    setShowCreateModal(false);
    navigate(`/project/${newProject.id}`);
  };

  const ProjectCard = ({ project }) => {
    const frameworkInfo = getFrameworkInfo(project.framework, FRAMEWORKS);

    // Show Python + FastAPI logos for FastAPI projects
    const showStackLogos = project.framework === 'fastapi';

    if (viewMode === 'list') {
      return (
        <div
          className="card p-4 cursor-pointer hover:shadow-[0_0_0_3px_#c8a951] transition-all"
          onClick={() => navigate(`/project/${project.id}`)}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4 flex-1">
              {showStackLogos ? (
                <div className="flex items-center gap-2">
                  <img src="/assets/python.svg" alt="Python" className="w-12 h-12" />
                  <span className="text-accent-gold text-2xl">+</span>
                  <img src="/assets/fastapi.svg" alt="FastAPI" className="w-12 h-12" />
                </div>
              ) : (
                <div className={`w-12 h-12 ${frameworkInfo.color} rounded-lg flex items-center justify-center text-2xl`}>
                  {frameworkInfo.icon}
                </div>
              )}
              <div>
                <h3 className="text-lg font-semibold text-gray-800">{project.name}</h3>
                <p className="text-sm text-gray-500">
                  {frameworkInfo.name} • v{project.version}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right mr-4">
                <p className="text-xs text-gray-500">Updated</p>
                <p className="text-sm text-gray-700">{formatDate(project.updated_at)}</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/project/${project.id}`);
                  }}
                  className="p-2 text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                  title="Edit"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteConfirm({ projectId: project.id, projectName: project.name });
                  }}
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div
        className="card p-6 cursor-pointer hover:shadow-[0_0_0_3px_#c8a951] transition-all"
        onClick={() => navigate(`/project/${project.id}`)}
      >
        <div className="flex justify-between items-start mb-4">
          {showStackLogos ? (
            <div className="flex items-center gap-2">
              <img src="/assets/python.svg" alt="Python" className="w-14 h-14" />
              <span className="text-accent-gold text-3xl font-bold">+</span>
              <img src="/assets/fastapi.svg" alt="FastAPI" className="w-14 h-14" />
            </div>
          ) : (
            <div className={`w-14 h-14 ${frameworkInfo.color} rounded-lg flex items-center justify-center text-3xl`}>
              {frameworkInfo.icon}
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/project/${project.id}`);
              }}
              className="p-2 text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
              title="Edit"
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setDeleteConfirm({ projectId: project.id, projectName: project.name });
              }}
              className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
              title="Delete"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        <h3 className="text-xl font-semibold text-gray-800 mb-2">{project.name}</h3>
        <div className="text-sm text-gray-500 mb-4">
          <p>{frameworkInfo.name}</p>
          <p>Version {project.version}</p>
        </div>

        <div className="border-t pt-3 mt-auto">
          <p className="text-xs text-gray-500">
            Updated {formatDate(project.updated_at)}
          </p>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="container mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-800 flex items-center gap-1">
                <StaticLogo
                  size="large"
                  onClick={() => navigate('/')}
                  className="hover:opacity-80 transition-opacity"
                />
                <span
                  className="cursor-pointer hover:text-primary-600 transition-colors"
                  onClick={() => navigate('/')}
                >
                  BackStudio
                </span>
              </h1>
              <p className="text-gray-600 mt-1">Manage your backend projects</p>
            </div>
            <Button onClick={() => setShowCreateModal(true)} className="flex items-center gap-2">
              <Plus className="w-5 h-5" />
              Create Project
            </Button>
          </div>
        </div>
      </div>

      {/* Search and View Controls */}
      <div className="container mx-auto px-6 py-6">
        <div className="flex justify-between items-center mb-6">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search projects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          <div className="flex gap-2 ml-4">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-2 rounded-lg transition-colors ${
                viewMode === 'grid'
                  ? 'bg-primary-100 text-primary-600'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
              title="Grid View"
            >
              <Grid3x3 className="w-5 h-5" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 rounded-lg transition-colors ${
                viewMode === 'list'
                  ? 'bg-primary-100 text-primary-600'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
              title="List View"
            >
              <List className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Projects Grid/List */}
        {loading ? (
          <div className="text-center py-20">
            <p className="text-gray-500">Loading projects...</p>
          </div>
        ) : filteredProjects.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-gray-500 mb-4">
              {searchQuery ? 'No projects found matching your search.' : 'No projects yet.'}
            </p>
            {!searchQuery && (
              <Button onClick={() => setShowCreateModal(true)} className="inline-flex items-center gap-2">
                <Plus className="w-5 h-5" />
                Create Your First Project
              </Button>
            )}
          </div>
        ) : (
          <div className={viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6' : 'space-y-4'}>
            {filteredProjects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}
      </div>

      {/* Create Project Modal */}
      {showCreateModal && (
        <CreateProjectModal
          onClose={() => setShowCreateModal(false)}
          onProjectCreated={handleProjectCreated}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title="Delete Project"
        message={`Are you sure you want to delete "${deleteConfirm?.projectName}"? This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        onConfirm={handleDeleteProject}
        onCancel={() => setDeleteConfirm(null)}
      />
    </div>
  );
}

export default Dashboard;
