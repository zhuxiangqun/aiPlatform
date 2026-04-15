import React from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  icon,
  className = '',
  ...props
}) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-300">
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            {icon}
          </div>
        )}
        <input
          className={`
            w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg
            text-sm text-gray-100 placeholder-gray-500
            transition-all duration-150
            hover:border-gray-500
            focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10
            disabled:bg-dark-bg disabled:text-gray-500 disabled:cursor-not-allowed
            ${icon ? 'pl-10' : ''}
            ${error ? 'border-error focus:border-error focus:ring-error/10' : ''}
            ${className}
          `}
          {...props}
        />
      </div>
      {error && (
        <p className="mt-1.5 text-sm text-error">{error}</p>
      )}
    </div>
  );
};

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea: React.FC<TextareaProps> = ({
  label,
  error,
  className = '',
  ...props
}) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-300">
          {label}
        </label>
      )}
      <textarea
        className={`
          w-full px-3 py-2 bg-dark-card border border-dark-border rounded-lg
          text-sm text-gray-100 placeholder-gray-500
          transition-all duration-150 resize-none
          hover:border-gray-500
          focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10
          disabled:bg-dark-bg disabled:text-gray-500 disabled:cursor-not-allowed
          ${error ? 'border-error focus:border-error focus:ring-error/10' : ''}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p className="mt-1.5 text-sm text-error">{error}</p>
      )}
    </div>
  );
};

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value?: string;
  onChange?: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  label?: string;
  error?: string;
  disabled?: boolean;
  className?: string;
}

export const Select: React.FC<SelectProps> = ({
  value,
  onChange,
  options,
  placeholder = '请选择',
  label,
  error,
  disabled,
  className = '',
}) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-300">
          {label}
        </label>
      )}
      <select
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={disabled}
        className={`
          w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg
          text-sm text-gray-100
          transition-all duration-150
          hover:border-gray-500
          focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10
          disabled:bg-dark-bg disabled:text-gray-500 disabled:cursor-not-allowed
          appearance-none cursor-pointer
          bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')]
          bg-[length:1.25rem] bg-[right_0.5rem_center] bg-no-repeat
          pr-10
          ${error ? 'border-error' : ''}
          ${className}
        `}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p className="mt-1.5 text-sm text-error">{error}</p>
      )}
    </div>
  );
};

export default Input;
