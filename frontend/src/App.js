import React from 'react';
import './App.css';
import './styles/datepicker.css';
import './styles/header.css';
import AppRoutes from './routes';
import { Toaster } from 'react-hot-toast';

const App = () => {
    return (
        <div>
            <AppRoutes />
            <Toaster position="top-right" reverseOrder={false} />
        </div>
    );
};

export default App;
