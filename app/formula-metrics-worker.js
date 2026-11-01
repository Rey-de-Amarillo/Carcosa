import {FootballData} from './workspace-data.js';
import {FormulaMetricsEngine,createFormulaMetricsRunner} from './formula-metrics.js';

const evaluate=createFormulaMetricsRunner(new FormulaMetricsEngine(new FootballData()),message=>self.postMessage(message));
self.addEventListener('message',event=>{void evaluate(event.data);});
