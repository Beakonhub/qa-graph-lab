// buiuld it using indempotently -system-under-test services ---
MERGE (auth:Service {name:'LoginService'})
MERGE (product:Service {name:'ProductService'})
MERGE (order:Service {name:'OrderService'})
MERGE (payment:Service {name:'PaymentService'})

// --- features depend on auth (directed!) ---
MERGE (product)-[:REQUIRES]->(auth)
MERGE (payment)-[:REQUIRES]->(auth)
MERGE (order)-[:REQUIRES]->(auth)

MERGE (:Test {name:'LoginTest'})-[:CALLS]->(auth)
MERGE (:Test {name:'CheckoutTest'})-[:CALLS]->(auth)
MERGE (:Test {name:'OrderTest'})-[:CALLS]->(auth)

// -- Count the number of service that require auth
// MATCH (s:Service)-[:REQUIRES]->(:Service {name:'LoginService'})
// RETURN count(s)

// -- Get the total number of node
//MATCH (n) RETURN count(n)        // note the number

// MATCH (t:Test)-[:CALLS]->(:Service)-[:REQUIRES]->(:Service {name:'LoginService'})
// RETURN DISTINCT t.name

// -- Which test break if Auth changes? - LoginTest(Direct Inpact), Orser/CHeckout(Indirect Inpact)
//--*0.. means "follow REQUIRES any number of times, including zero"--
MATCH (t:Test)-[:CALLS]->(s:Service)
WHERE (s)-[:REQUIRES*0..]->(:Service {name:'LoginService'})
RETURN DISTINCT t.name














