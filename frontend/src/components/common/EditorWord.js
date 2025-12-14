import React, { forwardRef } from 'react';
import { Editor } from '@tinymce/tinymce-react';

const EditorWord = forwardRef(({ value, onChange, placeholder }, ref) => {
  return (
    <div className="shadow-sm border border-gray-300 rounded-lg overflow-hidden" ref={ref}>
      <Editor
        apiKey="gwx0ng0w8dxomhgd4cltgiduy851u97tlh4fs9hgjb3od6a1"
        value={value}
        onEditorChange={(newValue) => {
          onChange(newValue);
        }}
        init={{
          height: 600,
          menubar: true,
          plugins: [
            'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
            'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
            'insertdatetime', 'media', 'table', 'code', 'help', 'wordcount'
          ],
          toolbar: 'undo redo | blocks | bold italic forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | image | help',
          content_style: 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px; background-color: #E8F4F8; padding: 40px; }',
          placeholder: placeholder || "Escribe aquí...",
          automatic_uploads: true,
          file_picker_types: 'image',
          images_upload_handler: (blobInfo) => new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(blobInfo.blob());
            reader.onload = () => {
              resolve(reader.result);
            };
            reader.onerror = (error) => reject(error);
          })
        }}
      />
    </div>
  );
});

EditorWord.displayName = 'EditorWord';

export default EditorWord;