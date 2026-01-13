// Format date to readable string
export const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

// Download file from blob
export const downloadFile = (blob, filename) => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

// Get framework icon and color
export const getFrameworkInfo = (frameworkId, frameworks) => {
  return frameworks.find(f => f.id === frameworkId) || frameworks[0];
};

// Count summary statistics for project state
export const getProjectStats = (projectState) => {
  if (!projectState) return { models: 0, services: 0, endpoints: 0, dependencies: 0 };

  return {
    models: projectState.models?.length || 0,
    services: projectState.services?.length || 0,
    endpoints: projectState.services?.reduce((acc, service) =>
      acc + (service.endpoints?.length || 0), 0) || 0,
    dependencies: projectState.dependencies?.length || 0,
  };
};

// Validate field name (alphanumeric and underscores only)
export const validateFieldName = (name) => {
  return /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name);
};

// Pluralize a word using simple English rules
const pluralize = (word) => {
  if (!word) return '';

  const lowerWord = word.toLowerCase();

  // Words that don't change in plural
  const unchanging = ['sheep', 'fish', 'deer', 'series', 'species', 'data', 'info'];
  if (unchanging.includes(lowerWord)) {
    return word;
  }

  // Irregular plurals
  const irregulars = {
    'person': 'people',
    'man': 'men',
    'woman': 'women',
    'child': 'children',
    'tooth': 'teeth',
    'foot': 'feet',
    'mouse': 'mice',
    'goose': 'geese',
  };
  if (irregulars[lowerWord]) {
    return irregulars[lowerWord];
  }

  // Words ending in 'y' preceded by a consonant
  if (/[^aeiou]y$/i.test(word)) {
    return word.slice(0, -1) + 'ies';
  }

  // Words ending in 's', 'ss', 'sh', 'ch', 'x', 'z'
  if (/(s|ss|sh|ch|x|z)$/i.test(word)) {
    return word + 'es';
  }

  // Words ending in 'f' or 'fe'
  if (/fe?$/i.test(word)) {
    return word.replace(/fe?$/i, 'ves');
  }

  // Words ending in 'o' preceded by a consonant
  if (/[^aeiou]o$/i.test(word)) {
    return word + 'es';
  }

  // Default: just add 's'
  return word + 's';
};

// Generate table name from model name (snake_case and pluralized)
// Examples: User -> users, UserSubscription -> user_subscriptions
export const generateTableName = (modelName) => {
  if (!modelName) return '';

  // Convert to snake_case
  const snakeCased = modelName
    .replace(/([a-z])([A-Z])/g, '$1_$2')
    .replace(/([0-9])([A-Z])/g, '$1_$2')
    .toLowerCase();

  // Split by underscore to get the last word for pluralization
  const parts = snakeCased.split('_');
  const lastWord = parts[parts.length - 1];

  // Pluralize the last word
  const pluralLastWord = pluralize(lastWord);

  // Replace the last word with its plural form
  parts[parts.length - 1] = pluralLastWord;

  return parts.join('_');
};

// Truncate text with ellipsis
export const truncate = (text, maxLength = 50) => {
  if (!text || text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

// Copy text to clipboard
export const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    console.error('Failed to copy:', err);
    return false;
  }
};

// Generate unique ID for client-side objects
export const generateId = () => {
  return `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
};
