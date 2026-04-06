import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { departmentsApi } from '../services/api';

const DepartmentContext = createContext(null);

const STORAGE_KEY = 'kr_timetable_selected_dept_id';

export function DepartmentProvider({ children }) {
    const [departments, setDepartments] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedDeptId, setSelectedDeptId] = useState(() => {
        try {
            return localStorage.getItem(STORAGE_KEY) || '';
        } catch {
            return '';
        }
    });

    const deptId = selectedDeptId ? Number(selectedDeptId) : null;

    const reloadDepartments = useCallback(async () => {
        setLoading(true);
        try {
            const res = await departmentsApi.getAll();
            setDepartments(res.data || []);
        } catch (err) {
            console.error('Failed to load departments', err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        let cancelled = false;

        (async () => {
            setLoading(true);
            try {
                const res = await departmentsApi.getAll();
                if (cancelled) return;
                setDepartments(res.data || []);
            } catch (err) {
                console.error('Failed to load departments', err);
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        })();

        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY, selectedDeptId || '');
        } catch {
            // ignore
        }
    }, [selectedDeptId]);

    const value = useMemo(
        () => ({
            departments,
            loading,
            selectedDeptId,
            setSelectedDeptId,
            deptId,
            reloadDepartments,
        }),
        [departments, loading, selectedDeptId, deptId, reloadDepartments]
    );

    return <DepartmentContext.Provider value={value}>{children}</DepartmentContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useDepartmentContext() {
    const ctx = useContext(DepartmentContext);
    if (!ctx) {
        throw new Error('useDepartmentContext must be used inside a DepartmentProvider');
    }
    return ctx;
}
