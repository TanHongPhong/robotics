import { createContext, useContext, useState, useEffect } from 'react';

const InventoryContext = createContext();

export function InventoryProvider({ children }) {
    const [items, setItems] = useState([]);
    const [isLoading, setIsLoading] = useState(true);

    // Load data from backend on mount + polling
    useEffect(() => {
        loadInventoryData();

        // 🔄 AUTO-RELOAD: Poll every 3 seconds to sync with backend file changes
        const pollInterval = setInterval(() => {
            loadInventoryData();
        }, 3000); // 3 seconds

        // Cleanup interval on unmount
        return () => {
            clearInterval(pollInterval);
        };
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
            // Fallback to default 16 items (4x4 grid) with YOLO class names
            const classNames = [
                "coca lon", "pepsi lon", "goi qua", "van tho",
                "cay quat", "siukay", "xuanay", "photron",
                "haohao", "omachi", "coca chai", "nuoc khoang",
                "ket sprite", "ket coca", "ket pepsi", "ket fanta"
            ];

            setItems(
                Array.from({ length: 16 }, (_, i) => ({
                    cell_id: i + 1,
                    product: classNames[i],
                    class_id: i,
                    pick: false,
                    done: false
                }))
            );
            setIsLoading(false);
        }
    };

    const togglePick = async (cellId) => {
        setItems(prevItems => {
            const newItems = prevItems.map(item => {
                if (item.cell_id === cellId) {
                    return {
                        ...item,
                        pick: !item.pick,
                        done: !item.pick ? false : item.done
                    };
                }
                return item;
            });

            // ✅ Save to backend immediately after user toggles
            setTimeout(async () => {
                try {
                    const qwenAPI = (await import('../services/qwenAPI')).default;
                    await qwenAPI.updateInventory({ items: newItems });
                    console.log('✅ Saved pick toggle to backend');
                } catch (error) {
                    console.error('❌ Failed to save pick toggle:', error);
                }
            }, 100);

            return newItems;
        });
    };

    const toggleDone = async (cellId) => {
        setItems(prevItems => {
            const newItems = prevItems.map(item => {
                if (item.cell_id === cellId && item.pick) {
                    return { ...item, done: !item.done };
                }
                return item;
            });

            // ✅ Save to backend immediately after user toggles
            setTimeout(async () => {
                try {
                    const qwenAPI = (await import('../services/qwenAPI')).default;
                    await qwenAPI.updateInventory({ items: newItems });
                    console.log('✅ Saved done toggle to backend');
                } catch (error) {
                    console.error('❌ Failed to save done toggle:', error);
                }
            }, 100);

            return newItems;
        });
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
