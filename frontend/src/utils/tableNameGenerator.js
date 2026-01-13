/**
 * Convert a PascalCase or camelCase string to snake_case
 * @param {string} str - The string to convert
 * @returns {string} - The snake_case string
 */
export function toSnakeCase(str) {
  if (!str) return '';

  return str
    // Insert underscore before uppercase letters that follow lowercase letters
    .replace(/([a-z])([A-Z])/g, '$1_$2')
    // Insert underscore before uppercase letters that follow numbers
    .replace(/([0-9])([A-Z])/g, '$1_$2')
    // Convert to lowercase
    .toLowerCase();
}

/**
 * Pluralize a word using simple English rules
 * @param {string} word - The word to pluralize
 * @returns {string} - The pluralized word
 */
export function pluralize(word) {
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
}

/**
 * Generate a table name from a model name
 * Converts to snake_case and pluralizes
 * @param {string} modelName - The model name (e.g., "UserSubscription")
 * @returns {string} - The table name (e.g., "user_subscriptions")
 */
export function generateTableName(modelName) {
  if (!modelName) return '';

  // Convert to snake_case
  const snakeCased = toSnakeCase(modelName);

  // Split by underscore to get the last word for pluralization
  const parts = snakeCased.split('_');
  const lastWord = parts[parts.length - 1];

  // Pluralize the last word
  const pluralLastWord = pluralize(lastWord);

  // Replace the last word with its plural form
  parts[parts.length - 1] = pluralLastWord;

  return parts.join('_');
}
