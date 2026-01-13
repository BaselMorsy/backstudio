import { useState, useEffect } from 'react';
import { FolderTree, Folder, File, ChevronRight, ChevronDown, FolderOpen } from 'lucide-react';
import { projectAPI } from '../../services/api';

function StructurePreviewTab({ projectId }) {
  const [loading, setLoading] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState({});
  const [structure, setStructure] = useState(null);
  const [projectState, setProjectState] = useState(null);

  useEffect(() => {
    fetchProjectState();
  }, [projectId]);

  const fetchProjectState = async () => {
    try {
      setLoading(true);
      const response = await projectAPI.getState(projectId);
      setProjectState(response.data);
      setStructure(buildStructure(response.data));
    } catch (error) {
      console.error('Failed to fetch project state:', error);
    } finally {
      setLoading(false);
    }
  };

  const buildStructure = (state) => {
    if (!state) return null;

    const structure = {
      name: state.name || 'project-root',
      type: 'folder',
      children: [],
    };

    // Add database folder with models
    if (state.data_models && state.data_models.length > 0) {
      structure.children.push({
        name: 'database',
        type: 'folder',
        children: [
          { name: '__init__.py', type: 'file' },
          { name: 'base.py', type: 'file' },
          { name: 'models.py', type: 'file' },
          { name: 'repo.py', type: 'file' },
        ],
      });
    }

    // Add service folders
    if (state.services && state.services.length > 0) {
      state.services.forEach((service) => {
        structure.children.push({
          name: service.name.toLowerCase().replace(/service$/i, '') + '_service',
          type: 'folder',
          children: [
            { name: '__init__.py', type: 'file' },
            { name: 'schemas.py', type: 'file' },
            { name: 'service.py', type: 'file' },
            { name: 'routes.py', type: 'file' },
          ],
        });
      });
    }

    // Add root level files
    structure.children.push({ name: 'dependencies.py', type: 'file' });
    structure.children.push({ name: 'middleware.py', type: 'file' });
    structure.children.push({ name: 'server.py', type: 'file' });
    structure.children.push({ name: 'requirements.txt', type: 'file' });
    structure.children.push({ name: 'README.md', type: 'file' });

    return structure;
  };

  const toggleFolder = (path) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [path]: !prev[path],
    }));
  };

  const renderNode = (node, level = 0, path = '') => {
    const indent = `${level * 1.5}rem`;
    const nodePath = path ? `${path}/${node.name}` : node.name;
    const isExpanded = expandedFolders[nodePath] ?? true; // Default to expanded

    if (node.type === 'file') {
      return (
        <div key={nodePath} className="flex items-center gap-2 py-1 hover:bg-gray-800 px-2 rounded cursor-default" style={{ paddingLeft: indent }}>
          <File className="w-4 h-4 text-blue-400" />
          <span className="text-sm text-gray-100">{node.name}</span>
        </div>
      );
    }

    return (
      <div key={nodePath}>
        <div
          className="flex items-center gap-2 py-1 hover:bg-gray-800 px-2 rounded cursor-pointer"
          style={{ paddingLeft: indent }}
          onClick={() => toggleFolder(nodePath)}
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-400" />
          )}
          {isExpanded ? (
            <FolderOpen className="w-4 h-4 text-yellow-400" />
          ) : (
            <Folder className="w-4 h-4 text-yellow-400" />
          )}
          <span className="text-sm font-medium text-gray-100">{node.name}</span>
        </div>
        {isExpanded && node.children && node.children.map((child) => renderNode(child, level + 1, nodePath))}
      </div>
    );
  };

  if (loading) {
    return <div className="text-center py-10">Loading project structure...</div>;
  }

  if (!structure) {
    return (
      <div className="text-center py-12">
        <FolderTree className="w-12 h-12 text-gray-400 mx-auto mb-3" />
        <p className="text-gray-500">No project structure available yet.</p>
        <p className="text-sm text-gray-400 mt-2">Add models and services to see the structure.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <FolderTree className="w-5 h-5 text-gray-600" />
        <h2 className="text-2xl font-bold text-gray-800">Project Structure Preview</h2>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="bg-gray-900 rounded-lg p-4 font-mono text-sm overflow-auto max-h-[600px]">
          <div className="text-gray-300">{renderNode(structure)}</div>
        </div>
        <p className="text-sm text-gray-500 mt-4">
          This is a preview of the generated folder structure based on your current project configuration.
        </p>
      </div>
    </div>
  );
}

export default StructurePreviewTab;
