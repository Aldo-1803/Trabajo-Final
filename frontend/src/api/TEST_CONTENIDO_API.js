/**
 * TEST: Verificar que el servicio API funciona correctamente
 * Ejecuta esto en la consola del navegador (F12 > Console)
 */

// Importar el servicio
import { contenidoEducativoAPI } from './src/api/contenidoEducativoAPI';

// ============================================
// TEST 1: Obtener contenidos publicados
// ============================================
async function testGetPublicados() {
    console.log('TEST 1: getPublicados()');
    try {
        const contenidos = await contenidoEducativoAPI.getPublicados();
        console.log('Contenidos cargados:', contenidos);
        return true;
    } catch (error) {
        console.error('Error:', error);
        return false;
    }
}

// ============================================
// TEST 2: Obtener contenido por ID
// ============================================
async function testGetById() {
    console.log('TEST 2: getById(1)');
    try {
        const contenido = await contenidoEducativoAPI.getById(1);
        console.log('Contenido cargado:', contenido);
        return true;
    } catch (error) {
        console.error('Error:', error);
        return false;
    }
}

// ============================================
// TEST 3: Dar like
// ============================================
async function testLike() {
    console.log('TEST 3: like(1)');
    try {
        const resultado = await contenidoEducativoAPI.like(1);
        console.log('Like registrado:', resultado);
        return true;
    } catch (error) {
        console.error('Error:', error);
        return false;
    }
}

// ============================================
// TEST 4: Guardar contenido
// ============================================
async function testGuardar() {
    console.log('TEST 4: guardar(1)');
    try {
        const resultado = await contenidoEducativoAPI.guardar(1);
        console.log('Contenido guardado:', resultado);
        return true;
    } catch (error) {
        console.error('Error:', error);
        return false;
    }
}

// ============================================
// TEST 5: Obtener mis guardados
// ============================================
async function testMisGuardados() {
    console.log('TEST 5: getMisGuardados()');
    try {
        const guardados = await contenidoEducativoAPI.getMisGuardados();
        console.log('Mis guardados:', guardados);
        return true;
    } catch (error) {
        console.error('Error:', error);
        return false;
    }
}

// ============================================
// EJECUTAR TODOS LOS TESTS
// ============================================
async function runAllTests() {
    console.log('Iniciando tests del servicio API de Contenido Educativo...\n');
    
    const results = [];
    results.push(await testGetPublicados());
    console.log('');
    
    results.push(await testGetById());
    console.log('');
    
    results.push(await testMisGuardados());
    console.log('');
    
    // Uncomment para probar like y guardar (estos pueden cambiar el estado)
    // results.push(await testLike());
    // console.log('');
    
    // results.push(await testGuardar());
    // console.log('');
    
    const passed = results.filter(r => r === true).length;
    const total = results.length;
    
    console.log(`\nResultados: ${passed}/${total} tests pasados`);
    if (passed === total) {
        console.log('Todos los tests pasaron.');
    } else {
        console.log('Algunos tests fallaron. Verifica los errores arriba.');
    }
}

// Ejecutar
// runAllTests();

/**
 * Para ejecutar en la consola del navegador:
 * 
 * 1. Abre las DevTools (F12)
 * 2. Ve a la pestaña Console
 * 3. Copia y pega el siguiente comando:
 * 
 *    runAllTests()
 * 
 * 4. Presiona Enter
 */
