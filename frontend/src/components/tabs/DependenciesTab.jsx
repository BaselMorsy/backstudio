import { useState, useEffect } from 'react';
import { Plus, Package, Edit2, Trash2 } from 'lucide-react';
import { dependencyAPI } from '../../services/api';
import { useToast } from '../common/ToastContainer';
import ConfirmDialog from '../common/ConfirmDialog';
import Button from '../common/Button';
import AddDependencyModal from '../modals/AddDependencyModal';
import EditDependencyModal from '../modals/EditDependencyModal';

function DependenciesTab({ projectId }) {
  const toast = useToast();
  const [dependencies, setDependencies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingDependency, setEditingDependency] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  useEffect(() => {
    fetchDependencies();
  }, [projectId]);

  const fetchDependencies = async () => {
    try {
      setLoading(true);
      const response = await dependencyAPI.getAll(projectId);
      setDependencies(response.data);
    } catch (error) {
      console.error('Failed to fetch dependencies:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = (dependencyId) => {
    setConfirmDelete(dependencyId);
  };

  const handleConfirmDelete = async () => {
    if (!confirmDelete) return;

    try {
      await dependencyAPI.delete(projectId, confirmDelete);
      setDependencies(dependencies.filter((d) => d.id !== confirmDelete));
      toast.showSuccess('Dependency deleted successfully');
    } catch (error) {
      console.error('Failed to delete dependency:', error);
      toast.showError(error.response?.data?.detail || 'Failed to delete dependency');
    } finally {
      setConfirmDelete(null);
    }
  };

  if (loading) {
    return <div className="text-center py-10">Loading...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <Package className="w-5 h-5 text-gray-600" />
          <h2 className="text-2xl font-bold text-gray-800">Dependencies</h2>
          <span className="bg-gray-200 text-gray-700 px-2 py-1 rounded-full text-sm">
            {dependencies.length}
          </span>
        </div>
        <Button onClick={() => setShowAddModal(true)} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Dependency
        </Button>
      </div>

      {dependencies.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border-2 border-dashed border-gray-300">
          <Package className="w-12 h-12 text-gray-400 mx-auto mb-3" />
          <p className="text-gray-500 mb-4">No dependency injections defined yet</p>
          <p className="text-sm text-gray-400 mb-4">
            Define guards and providers for dependency injection
          </p>
          <Button onClick={() => setShowAddModal(true)} className="inline-flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Add Your First Dependency
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {dependencies.map((dep) => (
            <div
              key={dep.id}
              className="card p-4 cursor-pointer hover:shadow-[0_0_0_3px_#c8a951] transition-all"
              onClick={() => setEditingDependency(dep)}
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-800">{dep.name}</h3>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded ${
                    dep.type === 'guard' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'
                  }`}>
                    {dep.type}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingDependency(dep);
                    }}
                    className="p-1.5 text-primary-600 hover:bg-primary-50 rounded transition-colors"
                    title="Edit"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(dep.id);
                    }}
                    className="p-1.5 text-red-600 hover:bg-red-50 rounded transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <p className="text-sm text-gray-600 mb-2">{dep.function_name}()</p>
              <p className="text-xs text-gray-500">Scope: {dep.scope}</p>
              {dep.description && <p className="text-sm text-gray-500 mt-2">{dep.description}</p>}
            </div>
          ))}
        </div>
      )}

      {showAddModal && (
        <AddDependencyModal
          projectId={projectId}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            fetchDependencies();
            setShowAddModal(false);
          }}
        />
      )}

      {editingDependency && (
        <EditDependencyModal
          dependency={editingDependency}
          projectId={projectId}
          onClose={() => setEditingDependency(null)}
          onSuccess={() => {
            fetchDependencies();
            setEditingDependency(null);
          }}
        />
      )}

      <ConfirmDialog
        isOpen={!!confirmDelete}
        title="Delete Dependency"
        message="Are you sure you want to delete this dependency?"
        confirmText="Delete"
        variant="danger"
        onConfirm={handleConfirmDelete}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}

export default DependenciesTab;
