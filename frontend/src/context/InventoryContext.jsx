import { createContext, useContext, useState, useEffect } from 'react';

const InventoryContext = createContext();

export function InventoryProvider({ children }) {
    const [items, setItems] = useState([]);
    const [isLoading, setIsLoading] = useState(true);

    // Load data from backend on mount
    useEffect(() => {
        loadInventoryData();
    }, []);

    const loadInventoryData = async () => {
        try {
            // Fetch from backend (source of truth)
            const response = await fetch('http://localhost:5000/api/inventory', {
                cache: 'no-store' // Always get fresh data
            });

            if (!response.ok) {
                throw new Error('Failed to fetch inventory');
            }

            const data = await response.json();
            setItems(data.items || []);
            setIsLoading(false);
        } catch (error) {
            console.error('Error loading inventory data:', error);
            // Fallback to default data
            setItems([
                { cell_id: 1, product: "", pick: false, done: false },
                { cell_id: 2, product: "", pick: false, done: false },
                { cell_id: 3, product: "", pick: false, done: false },
                { cell_id: 4, product: "", pick: false, done: false },
                { cell_id: 5, product: "", pick: false, done: false },
                { cell_id: 6, product: "", pick: false, done: false },
                { cell_id: 7, product: "", pick: false, done: false },
                { cell_id: 8, product: "", pick: false, done: false },
                { cell_id: 9, product: "", pick: false, done: false }
            ]);
            setIsLoading(false);
        }
    };

    const togglePick = (cellId) => {
        setItems(prevItems => prevItems.map(item => {
            if (item.cell_id === cellId) {
                return {
                    ...item,
                    pick: !item.pick,
                    done: !item.pick ? false : item.done
                };
            }
            return item;
        }));
    };

    const toggleDone = (cellId) => {
        setItems(prevItems => prevItems.map(item => {
            if (item.cell_id === cellId && item.pick) {
                return { ...item, done: !item.done };
            }
            return item;
        }));
    };

    const downloadJSON = () => {
        const dataStr = "data:text/json;charset=utf-8," +
            encodeURIComponent(JSON.stringify({ items }, null, 2));
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute("href", dataStr);
        downloadAnchor.setAttribute("download", "inventory.json");
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
    };

    const resetData = () => {
        localStorage.removeItem('robodoc-inventory');
        loadInventoryData();
    };

    const saveToBackend = async () => {
        try {
            const qwenAPI = (await import('../services/qwenAPI')).default;
            await qwenAPI.updateInventory({ items });
            console.log('✅ Inventory saved to backend');
        } catch (error) {
            console.error('❌ Failed to save inventory:', error);
        }
    };

    const updateItemsFromBackend = (newItems) => {
        setItems(newItems);
        localStorage.setItem('robodoc-inventory', JSON.stringify(newItems));
    };

    const value = {
        items,
        isLoading,
        togglePick,
        toggleDone,
        downloadJSON,
        resetData,
        saveToBackend,
        setItems: updateItemsFromBackend,
        reloadInventory: loadInventoryData
    };

    return (
        <InventoryContext.Provider value={value}>
            {children}
        </InventoryContext.Provider>
    );
}

export function useInventory() {
    const context = useContext(InventoryContext);
    if (!context) {
        throw new Error('useInventory must be used within InventoryProvider');
    }
    return context;
}
