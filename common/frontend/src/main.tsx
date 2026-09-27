import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { CommandBar } from './CommandBar';
import { Overlay } from './Overlay';
import './styles.css';

const route = window.location.pathname;
document.body.classList.toggle('route-overlay', route === '/overlay');
document.body.classList.toggle('route-command', route === '/command');

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);

root.render(
  <React.StrictMode>
    {route === '/overlay' ? (
      <Overlay />
    ) : route === '/command' ? (
      <CommandBar />
    ) : (
      <App />
    )}
  </React.StrictMode>,
);
