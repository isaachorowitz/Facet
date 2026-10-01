import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';
import './v2.css';
const root = document.getElementById('root');
if (!root) throw new Error('Missing Facet root');
createRoot(root).render(<App />);
