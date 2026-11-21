import { render, screen } from '@testing-library/react';

import App from './App';


jest.mock('./routes', () => () => <div>Rutas de la aplicación</div>);
jest.mock('./context/SessionContext', () => ({
    SessionProvider: ({children}) => <section aria-label="Sesión">{children}</section>,
}));
jest.mock('react-hot-toast', () => ({
    Toaster: () => <div aria-label="Notificaciones" />,
}));


test('renderiza el shell con sesión, rutas y notificaciones', () => {
    render(<App />);

    expect(screen.getByRole('region', {name: 'Sesión'})).toBeInTheDocument();
    expect(screen.getByText('Rutas de la aplicación')).toBeInTheDocument();
    expect(screen.getByLabelText('Notificaciones')).toBeInTheDocument();
});
