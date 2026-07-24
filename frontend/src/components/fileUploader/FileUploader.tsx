import "./FileUploader.css";

interface FileUploaderProps {
  selectedFile: File | null;
  disabled?: boolean;
  onFileChange: (file: File | null) => void;
  onRecognize: () => void;
}

function formatFileSize(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function FileUploader({
  selectedFile,
  disabled = false,
  onFileChange,
  onRecognize,
}: FileUploaderProps) {
  return (
    <div className="file-uploader">
      <div className="file-uploader__info">
        {selectedFile ? (
          <>
            <strong title={selectedFile.name}>
              {selectedFile.name}
            </strong>
            <span>
              {formatFileSize(selectedFile.size)} ·{" "}
              {selectedFile.type.startsWith("video/")
                ? "Бичлэг"
                : "Зураг"}
            </span>
          </>
        ) : (
          <span>Зураг эсвэл бичлэг сонгоно уу.</span>
        )}
      </div>

      <div className="file-uploader__actions">
        <label
          className={
            disabled
              ? "file-uploader__select file-uploader__select--disabled"
              : "file-uploader__select"
          }
        >
          Файл сонгох
          <input
            type="file"
            accept="image/*,video/*"
            disabled={disabled}
            onChange={(event) => {
              onFileChange(event.target.files?.[0] ?? null);
              event.target.value = "";
            }}
          />
        </label>

        <button
          type="button"
          className="file-uploader__recognize"
          disabled={!selectedFile || disabled}
          onClick={onRecognize}
        >
          {disabled ? "Танилт хийж байна..." : "Таних"}
        </button>
      </div>
    </div>
  );
}
