import { useEffect, useState } from 'react';
import axios from 'axios';

const DEFAULT_NOMBRE = 'Bohemia Hair';

const useEmpresaNombre = () => {
  const [empresaNombre, setEmpresaNombre] = useState(DEFAULT_NOMBRE);

  useEffect(() => {
    const fetchEmpresaNombre = async () => {
      try {
        const res = await axios.get('http://127.0.0.1:8000/api/gestion/configuracion/publica/');
        const nombre = res.data?.empresa_nombre?.trim();
        if (nombre) {
          setEmpresaNombre(nombre);
        }
      } catch (error) {
        console.error('Error cargando nombre de empresa:', error);
      }
    };

    fetchEmpresaNombre();
  }, []);

  return empresaNombre;
};

export default useEmpresaNombre;
