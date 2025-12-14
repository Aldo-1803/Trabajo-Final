import React from 'react';
import DOMPurify from 'dompurify';

const VisorHTML = ({ contenido, titulo = "Previsualizacion" }) => {
  // Sanitizar el HTML para evitar inyecciones XSS
  const sanitizedHTML = DOMPurify.sanitize(contenido || '');

  // Contar caracteres sin HTML
  const plainText = contenido?.replace(/<[^>]*>/g, '') || '';
  const charCount = plainText.length;

  return (
    <div className="bg-white rounded-lg border border-gray-300 overflow-hidden shadow-sm">
      {/* Header */}
      <div className="bg-gradient-to-r from-pink-500 to-rose-500 px-6 py-3">
        <h3 className="text-white font-bold">{titulo}</h3>
      </div>

      {/* Contenido */}
      <div className="p-6 min-h-64 max-h-96 overflow-y-auto">
        {contenido ? (
          <div
            className="text-gray-700 space-y-4"
            dangerouslySetInnerHTML={{ __html: sanitizedHTML }}
            style={{
              fontSize: '14px',
              lineHeight: '1.6',
            }}
          />
        ) : (
          <p className="text-gray-400 italic text-center py-20">El contenido aparecerá aquí...</p>
        )}
      </div>

      {/* Footer con info */}
      <div className="bg-gray-50 px-6 py-3 border-t border-gray-200 text-xs text-gray-600 flex justify-between">
        <span>Caracteres: <strong>{charCount}</strong></span>
        <span>Palabras: <strong>{plainText.split(/\s+/).filter(w => w.length > 0).length}</strong></span>
      </div>
    </div>
  );
};

export default VisorHTML;