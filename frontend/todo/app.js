// Simple To-Do app using localStorage
(() => {
  const STORAGE_KEY = 'raymond_todos_v1';

  // Elements
  const form = document.getElementById('todo-form');
  const input = document.getElementById('todo-input');
  const list = document.getElementById('todo-list');
  const countEl = document.getElementById('count');
  const filterButtons = document.querySelectorAll('.filters button');
  const clearCompletedBtn = document.getElementById('clear-completed');

  let todos = [];
  let filter = 'all'; // all | active | completed

  // Load/save
  function loadTodos() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      todos = raw ? JSON.parse(raw) : [];
    } catch (e) {
      todos = [];
      console.error('Failed to load todos', e);
    }
  }

  function saveTodos() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
    } catch (e) {
      console.error('Failed to save todos', e);
    }
  }

  // CRUD
  function addTodo(text) {
    const t = {
      id: Date.now().toString(),
      text: text.trim(),
      completed: false,
      createdAt: new Date().toISOString()
    };
    todos.unshift(t);
    saveTodos();
    render();
  }

  function toggleTodo(id) {
    todos = todos.map(t => t.id === id ? {...t, completed: !t.completed} : t);
    saveTodos();
    render();
  }

  function deleteTodo(id) {
    todos = todos.filter(t => t.id !== id);
    saveTodos();
    render();
  }

  function clearCompleted() {
    todos = todos.filter(t => !t.completed);
    saveTodos();
    render();
  }

  // Rendering
  function filteredTodos() {
    if (filter === 'active') return todos.filter(t => !t.completed);
    if (filter === 'completed') return todos.filter(t => t.completed);
    return todos;
  }

  function render() {
    // Clear
    list.innerHTML = '';
    const items = filteredTodos();

    if (items.length === 0) {
      const el = document.createElement('li');
      el.textContent = 'No tasks';
      el.style.padding = '12px';
      el.style.background = 'var(--card)';
      list.appendChild(el);
    } else {
      for (const t of items) {
        const li = document.createElement('li');
        li.className = t.completed ? 'completed' : '';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = t.completed;
        checkbox.addEventListener('change', () => toggleTodo(t.id));

        const span = document.createElement('div');
        span.className = 'text';
        span.textContent = t.text;

        const actions = document.createElement('div');
        actions.className = 'actions';

        const del = document.createElement('button');
        del.title = 'Delete';
        del.innerHTML = '🗑';
        del.addEventListener('click', () => {
          if (confirm('Delete this task?')) deleteTodo(t.id);
        });

        actions.appendChild(del);

        li.appendChild(checkbox);
        li.appendChild(span);
        li.appendChild(actions);

        list.appendChild(li);
      }
    }

    // Count
    const remaining = todos.filter(t => !t.completed).length;
    countEl.textContent = `${remaining} item${remaining !== 1 ? 's' : ''}`;
    // Update filter buttons active state
    filterButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.filter === filter));
  }

  // Events
  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const value = input.value || '';
    if (value.trim().length === 0) return;
    addTodo(value);
    input.value = '';
    input.focus();
  });

  filterButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      filter = btn.dataset.filter;
      render();
    });
  });

  clearCompletedBtn.addEventListener('click', () => {
    if (confirm('Clear all completed tasks?')) clearCompleted();
  });

  // Init
  loadTodos();
  render();

  // Expose for debugging in console
  window.RaymondTodo = {
    list: () => todos,
    clearAll: () => { todos = []; saveTodos(); render(); }
  };
})();
