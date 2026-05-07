import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { CommandBar } from './CommandBar';
import { Overlay } from './Overlay';
import './styles.css';

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);

root.render(
  <React.StrictMode>
    {window.location.pathname === '/overlay' ? (
      <Overlay />
    ) : window.location.pathname === '/command' ? (
      <CommandBar />
    ) : (
      <App />
    )}
  </React.StrictMode>,
);
