import React from 'react';
import './App.css';
import './styles/datepicker.css';
import AppRoutes from './routes';
import { Toaster } from 'react-hot-toast';
import { SessionProvider } from './context/SessionContext';

const App = () => {
    return (
        <SessionProvider>
            <div>
                <AppRoutes />
                <Toaster position="top-right" reverseOrder={false} />
            </div>
        </SessionProvider>
    );
};

export default App;
